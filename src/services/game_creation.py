"""Скрипт для создания и управления играми."""

from dataclasses import dataclass
from datetime import datetime, time
from typing import Any

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, User

from src.config import logger
from src.database.db import Database
from src.services.core import NotificationService
from src.shared.decorators import handle_service_errors
from src.shared.formatters import Formatters
from src.shared.keyboards import CommonKeyboards, PaginationHelper
from src.shared.responses import ServiceResponse
from src.services.scheduler import ReminderSystem

router = Router()


@dataclass
class GameCreationConfig:
    """Конфигурация создания игр."""

    min_duration: int = 60
    max_duration: int = 180
    games_per_page: int = 4
    auto_register_creator: bool = True


class GameCreation(StatesGroup):
    """Состояния создания игры."""

    waiting_for_date = State()
    waiting_for_time = State()
    waiting_for_duration = State()
    waiting_for_location = State()
    waiting_for_court = State()


class DateTimeParser:
    """Парсер даты и времени."""

    @staticmethod
    def parse_date(date_text: str) -> datetime:
        """Парсинг даты из текста."""
        date_text = date_text.strip()

        # Формат ДД.ММ
        if len(date_text.split(".")) == 2:  # noqa: PLR2004
            day, month = date_text.split(".")
            year = datetime.now().year  # noqa: DTZ005
            if int(month) < datetime.now().month:  # noqa: DTZ005
                year += 1
            date_str = f"{day}.{month}.{year}"
        else:  # Формат ДД.ММ.ГГГГ
            date_str = date_text

        parsed_date = datetime.strptime(date_str, "%d.%m.%Y")  # noqa: DTZ007

        # Проверка, что дата не в прошлом
        if parsed_date.date() < datetime.now().date():  # noqa: DTZ005
            msg = "Дата не может быть в прошлом"
            raise ValueError(msg)

        return parsed_date

    @staticmethod
    def parse_time(time_text: str) -> time:
        """Парсинг времени из текста."""
        return datetime.strptime(time_text.strip(), "%H:%M").time()  # noqa: DTZ007

    @staticmethod
    def validate_duration(duration: int, config: GameCreationConfig) -> bool:
        """Валидация продолжительности."""
        return config.min_duration <= duration <= config.max_duration


class GameCreationService:
    """Сервис создания игр."""

    def __init__(  # noqa: D107
            self,
            db: Database,
            bot: Bot,
            reminder_system: ReminderSystem | None = None,
            config: GameCreationConfig | None = None,
    ) -> None:
        self.db = db
        self.bot = bot
        self.reminder_system = reminder_system
        self.config = config or GameCreationConfig()

    @handle_service_errors("Ошибка создания игры")
    async def create_game(self, game_data: dict[str, Any], creator: User) -> ServiceResponse:
        """Создать игру."""

        # Создание игры в БД
        success = await self.db.create_game(
            date=game_data["date"],
            time=game_data["time"],
            duration=game_data["duration"],
            location=game_data["location"],
            court=game_data["court"],
            admin=creator.id,
        )

        if not success:
            return ServiceResponse.error_response(
                "❌ Ошибка создания игры. Возможно, игра на эту дату уже существует."
            )

        # Автоматическая регистрация создателя
        if self.config.auto_register_creator:
            await self.db.register_player(game_data["date"], creator.id)

        # Планирование напоминания
        if self.reminder_system:
            await self.reminder_system.schedule_reminder(
                game_data["date"].date(),
                game_data["time"],
            )

        return ServiceResponse.success_response(
            "✅ Игра успешно создана",
            data={"game_data": game_data, "creator": creator},
            alert=False,
        )

    @handle_service_errors("Ошибка удаления игры")
    async def delete_game(self, game_date: datetime, user: User) -> ServiceResponse:
        """Удалить игру."""

        # Получить игру
        game = await self.db.get_game_by_date(game_date)
        if not game:
            return ServiceResponse.error_response("❌ Игра не найдена")

        # Проверить права
        if game.admin != user.id:
            return ServiceResponse.error_response("❌ Вы можете удалять только свои игры")

        # Получить список игроков для уведомления
        players = game.get_players()

        # Удалить игру
        success = await self.db.delete_game(game_date, user.id)
        if success:
            return ServiceResponse.success_response(
                "✅ Игра удалена",
                data={
                    "players": [p for p in players if p != user.id],
                    "date_formatted": Formatters.format_date(game_date),
                },
                alert=False,
            )
        else:
            return ServiceResponse.error_response("❌ Ошибка удаления игры")


class GameManagementKeyboards:
    """Клавиатуры для управления играми."""

    @staticmethod
    def create_main_menu() -> InlineKeyboardMarkup:
        """Главное меню управления играми."""
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Создать игру", callback_data="create_game")],
            [InlineKeyboardButton(text="🗑 Удаление игры", callback_data="my_created_games_0")],
            CommonKeyboards.create_back_to_main_button(),
        ])

    @staticmethod
    def create_cancel_keyboard() -> InlineKeyboardMarkup:
        """Клавиатура с кнопкой отмены."""
        return CommonKeyboards.create_cancel_keyboard()

    @staticmethod
    async def create_my_games_keyboard(
            db: Database,
            user_id: int,
            page: int = 0,
            config: GameCreationConfig | None = None,
    ) -> InlineKeyboardMarkup:
        """Клавиатура с созданными пользователем играми."""
        if not config:
            config = GameCreationConfig()

        offset = page * config.games_per_page
        games = await db.get_created_games(user_id, limit=config.games_per_page, offset=offset)
        total_count = await db.count_created_games(user_id)
        total_pages = (total_count + config.games_per_page - 1) // config.games_per_page

        keyboard = []

        # Кнопки с играми
        for game in games:
            date_str = Formatters.format_short_date(game.date)
            time_str = f" в {game.time}" if game.time else ""
            button_text = f"🗑 {date_str}{time_str}"
            callback_data = f"delete_game_{game.date.strftime('%Y-%m-%d')}"
            keyboard.append([InlineKeyboardButton(text=button_text, callback_data=callback_data)])

        # Навигация
        nav_buttons = PaginationHelper.create_navigation_buttons("my_created_games", page, total_pages)
        if nav_buttons:
            keyboard.append(nav_buttons)

        keyboard.append(CommonKeyboards.create_back_to_main_button())

        return InlineKeyboardMarkup(inline_keyboard=keyboard)


class GameCreationMessages:
    """Сообщения для создания игр."""

    @staticmethod
    def get_date_prompt() -> str:
        """Запрос даты."""
        return (
            "📅 <b>Создание новой игры</b>\n\n"
            "Введите дату игры в формате ДД.ММ.ГГГГ или ДД.ММ\n"
            "Например: 25.12.2024 или 25.12"
        )

    @staticmethod
    def get_time_prompt() -> str:
        """Запрос времени."""
        return "🕐 <b>Время игры</b>\n\nВведите время начала игры в формате ЧЧ:ММ\nНапример: 19:30"

    @staticmethod
    def get_duration_prompt(config: GameCreationConfig) -> str:
        """Запрос продолжительности."""
        return (
            f"⏱ <b>Продолжительность игры</b>\n\n"
            f"Введите продолжительность в минутах "
            f"(от {config.min_duration} до {config.max_duration}):"
        )

    @staticmethod
    def get_location_prompt() -> str:
        """Запрос локации."""
        return "📍 <b>Локация</b>\n\nВведите адрес или название места проведения игры:"

    @staticmethod
    def get_court_prompt() -> str:
        """Запрос номера корта."""
        return "🎾 <b>Номер корта</b>\n\nВведите номер корта"

    @staticmethod
    def format_success_message(game_data: dict[str, Any]) -> str:
        """Сообщение об успешном создании."""
        return Formatters.format_game_success_message(game_data)

    @staticmethod
    def format_notification_message(game_data: dict[str, Any], creator: User) -> str:
        """Уведомление о новой игре."""
        return Formatters.format_game_notification_message(game_data, creator)


# Глобальные сервисы
game_creation_service: GameCreationService | None = None
game_creation_config: GameCreationConfig | None = None


def init_game_management(
        db: Database,
        bot: Bot,
        reminder_system: ReminderSystem | None = None,
        config: GameCreationConfig | None = None,
) -> None:
    """Инициализировать управление играми."""
    global game_creation_service, game_creation_config  # noqa: PLW0603
    game_creation_config = config or GameCreationConfig()
    game_creation_service = GameCreationService(db, bot, reminder_system, game_creation_config)


# Обработчики
@router.callback_query(F.data == "game_management")
async def game_management_menu(callback: CallbackQuery) -> None:
    """Меню управления играми."""
    text = "🎮 <b>Управление играми</b>\n\nВыберите действие:"
    await callback.message.edit_text(
        text,
        reply_markup=GameManagementKeyboards.create_main_menu(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "create_game")
async def start_game_creation(callback: CallbackQuery, state: FSMContext) -> None:
    """Начало создания игры."""
    text = GameCreationMessages.get_date_prompt()
    keyboard = GameManagementKeyboards.create_cancel_keyboard()

    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await state.set_state(GameCreation.waiting_for_date)
    await callback.answer()


@router.message(GameCreation.waiting_for_date)
async def process_date(message: Message, state: FSMContext) -> None:
    """Обработка ввода даты."""
    try:
        game_date = DateTimeParser.parse_date(message.text)
        await state.update_data(date=game_date)

        text = GameCreationMessages.get_time_prompt()
        keyboard = GameManagementKeyboards.create_cancel_keyboard()

        await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
        await state.set_state(GameCreation.waiting_for_time)

    except ValueError as e:
        if "прошлом" in str(e):
            await message.answer("❌ Дата не может быть в прошлом. Попробуйте снова:")
        else:
            await message.answer("❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ или ДД.ММ")


@router.message(GameCreation.waiting_for_time)
async def process_time(message: Message, state: FSMContext) -> None:
    """Обработка ввода времени."""
    try:
        game_time = DateTimeParser.parse_time(message.text)
        await state.update_data(time=game_time)

        text = GameCreationMessages.get_duration_prompt(game_creation_config)
        keyboard = GameManagementKeyboards.create_cancel_keyboard()

        await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
        await state.set_state(GameCreation.waiting_for_duration)

    except ValueError:
        await message.answer("❌ Неверный формат времени. Используйте ЧЧ:ММ (например: 19:30)")


@router.message(GameCreation.waiting_for_duration)
async def process_duration(message: Message, state: FSMContext) -> None:
    """Обработка ввода продолжительности."""
    try:
        duration = int(message.text.strip())

        if not DateTimeParser.validate_duration(duration, game_creation_config):
            await message.answer(
                f"❌ Продолжительность должна быть от {game_creation_config.min_duration} "
                f"до {game_creation_config.max_duration} минут. Попробуйте снова:",
            )
            return

        await state.update_data(duration=duration)

        text = GameCreationMessages.get_location_prompt()
        keyboard = GameManagementKeyboards.create_cancel_keyboard()

        await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
        await state.set_state(GameCreation.waiting_for_location)

    except ValueError:
        await message.answer(
            f"❌ Введите число от {game_creation_config.min_duration} "
            f"до {game_creation_config.max_duration}",
        )


@router.message(GameCreation.waiting_for_location)
async def process_location(message: Message, state: FSMContext) -> None:
    """Обработка ввода локации."""
    location = message.text.strip()
    await state.update_data(location=location)

    text = GameCreationMessages.get_court_prompt()
    keyboard = GameManagementKeyboards.create_cancel_keyboard()

    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    await state.set_state(GameCreation.waiting_for_court)


@router.message(GameCreation.waiting_for_court)
async def process_court(message: Message, state: FSMContext) -> None:
    """Обработка ввода номера корта и создание игры."""
    try:
        court = int(message.text.strip())
        game_data = await state.get_data()
        game_data["court"] = court

        # Создание игры
        result = await game_creation_service.create_game(game_data, message.from_user)

        if result.success:
            # Сообщение создателю
            success_text = GameCreationMessages.format_success_message(game_data)
            await message.answer(
                success_text,
                reply_markup=CommonKeyboards.create_main_keyboard(),
                parse_mode="HTML",
            )

            # Уведомление всем пользователям в фоне
            notification_text = GameCreationMessages.format_notification_message(
                game_data, message.from_user,
            )
            NotificationService.send_to_all_users_async(
                game_creation_service.bot,
                game_creation_service.db,
                notification_text,
                exclude_user_id=message.from_user.id,
            )
        else:
            await message.answer(result.message)

        await state.clear()

    except ValueError:
        await message.answer("❌ Номер корта должен быть числом. Попробуйте снова:")


@router.callback_query(F.data.startswith("my_created_games_"))
async def show_my_created_games(callback: CallbackQuery, db: Database) -> None:
    """Показать созданные пользователем игры."""
    page = int(callback.data.split("_")[-1])

    games = await db.get_created_games(
        callback.from_user.id,
        limit=game_creation_config.games_per_page,
        offset=page * game_creation_config.games_per_page,
    )

    text = ("🚫 Вы не создавали игр" if not games
            else "🗑 <b>Мои созданные игры</b>\n\nВыберите игру для удаления:\n\n")

    keyboard = await GameManagementKeyboards.create_my_games_keyboard(
        db, callback.from_user.id, page, game_creation_config,
    )

    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("delete_game_"))
async def delete_game(callback: CallbackQuery) -> None:
    """Удаление игры."""
    date_str = callback.data.split("_")[2]
    game_date = datetime.strptime(date_str, "%Y-%m-%d")  # noqa: DTZ007

    result = await game_creation_service.delete_game(game_date, callback.from_user)

    if result.success:
        data = result.data or {}
        await callback.answer(f"✅ Игра на {data.get('date_formatted', '')} удалена", show_alert=True)

        # Уведомить игроков об отмене
        players = data.get("players", [])
        if players:
            creator_name = Formatters.get_display_name(callback.from_user)
            notification_text = (
                f"❌ <b>Игра отменена</b>\n\n"
                f"Создатель {creator_name} отменил игру на <b>{data.get('date_formatted', '')}</b>\n"
                f"Извините за неудобства!"
            )

            # Отправить уведомления игрокам в фоне
            NotificationService.send_to_players_async(
                game_creation_service.bot, notification_text, players
            )

        # Возврат в главное меню
        text = "🎾 <b>Добро пожаловать в бот записи на падел!</b>\n\nЧто хотите сделать?"
        await callback.message.edit_text(
            text,
            reply_markup=CommonKeyboards.create_main_keyboard(),
            parse_mode="HTML",
        )
    else:
        await callback.answer(result.message, show_alert=True)
