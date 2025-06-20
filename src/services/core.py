"""Классы для работы бота."""
from dataclasses import dataclass
from datetime import datetime

from aiogram import Bot
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, User

from src.config import logger
from src.database.db import Database


@dataclass
class BotConfig:
    """Конфигурация бота."""

    games_per_page: int = 4
    notification_enabled: bool = True


class UserFormatter:
    """Утилиты для форматирования пользователей."""

    @staticmethod
    def get_display_name(user: User) -> str:
        """Получить отображаемое имя пользователя."""
        if user.username:
            return f"@{user.username}"
        if user.first_name:
            return user.first_name
        return f"User{user.id}"


class GameFormatter:
    """Утилиты для форматирования игр."""

    @staticmethod
    def format_date(date: datetime) -> str:
        """Форматировать дату."""
        return date.strftime("%d.%m.%Y")

    @staticmethod
    def format_short_date(date: datetime) -> str:
        """Форматировать короткую дату."""
        return date.strftime("%d.%m")

    @staticmethod
    def format_time_duration(time: str, duration: int) -> str:
        """Форматировать время и длительность."""
        time_info = time
        if duration:
            hours = duration // 60
            minutes = duration % 60
            if minutes == 0:
                time_info += f" ({hours}ч)"
            else:
                time_info += f" ({hours}ч {minutes}м)"
        return time_info

    @staticmethod
    async def format_games_list(games: list, users_info: dict[int, str] | None = None) -> str:
        """Форматировать список игр для отображения."""
        if not games:
            return "🚫 Нет доступных игр"

        text = ""
        for game in games:
            date_str = GameFormatter.format_date(game.date)
            players_count = len(game.get_players())
            free_slots = game.free_slots()
            status_emoji = "🔍" if free_slots > 0 else "✅"

            # Основная информация об игре
            text += f"{status_emoji} <b>{date_str}</b>  "

            # Время и длительность
            if game.time:
                time_info = GameFormatter.format_time_duration(game.time, game.duration)
                text += f"{time_info}\n"

            # Локация и корт
            if game.location:
                text += f"📍 {game.location}\n"
            text += f"🎾 Корт №{game.court if game.court else 'не указан'}\n"

            # Участники
            if players_count > 0:
                if users_info:
                    player_names = [
                        users_info.get(player_id, f"User{player_id}")
                        for player_id in game.get_players()
                    ]
                    text += f"👥 Записаны: {', '.join(player_names)}\n"
                else:
                    text += f"👥 Записаны: {players_count} игрок(ов)\n"

            text += "\n"

        return text


class KeyboardBuilder:
    """Построитель клавиатур."""

    @staticmethod
    def create_main_keyboard() -> InlineKeyboardMarkup:
        """Создать главную клавиатуру."""
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🟢 Все игры", callback_data="show_available_games_0")],
            [InlineKeyboardButton(text="👤 Мои записи", callback_data="show_my_games_0")],
            [InlineKeyboardButton(text="📝 Записаться", callback_data="register_menu_0")],
            [InlineKeyboardButton(text="❌ Удалиться", callback_data="unregister_menu_0")],
            [InlineKeyboardButton(text="🎮 Управление играми", callback_data="game_management")],
        ])

    @staticmethod
    def create_navigation_buttons(action: str, page: int, total_pages: int) -> list[InlineKeyboardButton]:
        """Создать кнопки навигации."""
        nav_buttons = []

        if page > 0:
            nav_buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"{action}_{page - 1}"))

        if total_pages > 1:
            nav_buttons.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="current_page"))

        if page < total_pages - 1:
            nav_buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"{action}_{page + 1}"))

        return nav_buttons

    @staticmethod
    def create_games_list_keyboard(
            action: str,
            page: int,
            total_pages: int,
            additional_buttons: list[list[InlineKeyboardButton]] | None = None,
    ) -> InlineKeyboardMarkup:
        """Создать клавиатуру для списка игр."""
        keyboard = []

        # Навигация
        nav_buttons = KeyboardBuilder.create_navigation_buttons(action, page, total_pages)
        if nav_buttons:
            keyboard.append(nav_buttons)

        # Дополнительные кнопки
        if additional_buttons:
            keyboard.extend(additional_buttons)

        # Главное меню
        keyboard.append([InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")])

        return InlineKeyboardMarkup(inline_keyboard=keyboard)

    @staticmethod
    async def create_date_selection_keyboard(
            db: Database,
            action: str,
            user_id: int | None = None,
            page: int = 0,
            config: BotConfig | None = None,
    ) -> InlineKeyboardMarkup:
        """Создать клавиатуру выбора даты с пагинацией."""
        if not config:
            config = BotConfig()

        offset = page * config.games_per_page

        # Получение игр в зависимости от действия
        if action == "register":
            games = await db.get_available_games(
                limit=config.games_per_page,
                offset=offset,
                exclude_user_id=user_id,
            )
            total_count = (
                await db.count_available_games_excluding_user(user_id)
                if user_id else await db.count_available_games()
            )
        elif action == "unregister" and user_id:
            games = await db.get_user_games(user_id, limit=config.games_per_page, offset=offset)
            total_count = await db.count_user_games(user_id)
        else:
            return InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")],
            ])

        keyboard = []

        # Кнопки с играми
        for game in games:
            button_text = GameFormatter.format_short_date(game.date)

            if game.time:
                button_text += f" в {game.time}"
            else:
                button_text += " (время не указано)"

            if action == "register":
                free_slots = game.free_slots()
                button_text += f" (свободно: {free_slots})"
                callback_data = f"register_{game.date.strftime('%Y-%m-%d')}"
            else:  # unregister
                callback_data = f"unregister_{game.date.strftime('%Y-%m-%d')}"

            keyboard.append([InlineKeyboardButton(text=button_text, callback_data=callback_data)])

        # Навигация
        total_pages = (total_count + config.games_per_page - 1) // config.games_per_page
        nav_buttons = KeyboardBuilder.create_navigation_buttons(f"{action}_menu", page, total_pages)
        if nav_buttons:
            keyboard.append(nav_buttons)

        keyboard.append([InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")])

        return InlineKeyboardMarkup(inline_keyboard=keyboard)


class NotificationService:
    """Сервис уведомлений."""

    @staticmethod
    async def send_to_all_users(
            bot: Bot,
            db: Database,
            message: str,
            exclude_user_id: int | None = None,
    ) -> dict[str, int]:
        """Отправить уведомление всем пользователям."""
        stats = {"sent": 0, "failed": 0}

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🗑 Удалить уведомление", callback_data="delete_message")],
        ])

        try:
            all_users = await db.get_all_users()
            for user_id in all_users:
                if exclude_user_id and user_id == exclude_user_id:
                    continue
                try:
                    await bot.send_message(
                        user_id,
                        message,
                        parse_mode="HTML",
                        reply_markup=keyboard,
                    )
                    stats["sent"] += 1
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"Не удалось отправить уведомление пользователю {user_id}: {e}")
                    stats["failed"] += 1
            logger.info(f"Уведомления отправлены: {stats['sent']} успешно, {stats['failed']} неудачно")
        except Exception as e:  # noqa: BLE001
            logger.error(f"Ошибка при отправке уведомлений: {e}")
        return stats


class GameService:
    """Сервис для работы с играми."""

    def __init__(self, db: Database, bot: Bot, reminder_system=None, config: BotConfig | None = None) -> None:  # noqa: D107, ANN001
        self.db = db
        self.bot = bot
        self.reminder_system = reminder_system
        self.config = config or BotConfig()

    async def get_users_for_games(self, games: list) -> dict[int, str]:
        """Получить информацию о пользователях для списка игр."""
        all_player_ids = set()
        for game in games:
            all_player_ids.update(game.get_players())

        return await self.db.get_users_info(list(all_player_ids)) if all_player_ids else {}

    async def register_player(self, game_date: datetime, user: User) -> dict:
        """Записать игрока на игру."""
        result = {"success": False, "message": "", "alert": True}

        # Получить игру
        game = await self.db.get_game_by_date(game_date)
        if not game:
            result["message"] = "❌ Игра не найдена"
            return result

        if game.has_player(user.id):
            result["message"] = "⚠️ Вы уже записаны на эту игру"
            return result

        if game.is_full():
            result["message"] = "❌ Нет свободных мест"
            return result

        # Записать игрока
        success = await self.db.register_player(game_date, user.id)
        if success:
            date_formatted = GameFormatter.format_date(game_date)
            user_name = UserFormatter.get_display_name(user)

            result["success"] = True
            result["message"] = f"✅ Вы записаны на {date_formatted}"

            # Запланировать напоминание через reminder_system
            updated_game = await self.db.get_game_by_date(game_date)
            if updated_game and updated_game.time and self.reminder_system:
                try:
                    await self.reminder_system.schedule_reminder(game_date.date(), updated_game.time)
                    logger.debug(f"Напоминание запланировано для игры {date_formatted}")
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"Ошибка планирования напоминания: {e}")

            # Отправить уведомление
            if self.config.notification_enabled:
                notification_message = (
                    f"🎾 <b>Новая запись на игру!</b>\n\n"
                    f"{user_name} записался/-лась на <b>{date_formatted}</b>"
                )
                await NotificationService.send_to_all_users(
                    self.bot, self.db, notification_message, exclude_user_id=user.id,
                )
        else:
            result["message"] = "❌ Ошибка записи"

        return result

    async def unregister_player(self, game_date: datetime, user: User) -> dict:
        """Отписать игрока от игры."""
        result = {"success": False, "message": "", "alert": True}

        # Получить игру
        game = await self.db.get_game_by_date(game_date)
        if not game:
            result["message"] = "❌ Игра не найдена"
            return result

        if not game.has_player(user.id):
            result["message"] = "⚠️ Вы не записаны на эту игру"
            return result

        # Отписать игрока
        success = await self.db.unregister_player(game_date, user.id)
        if success:
            date_formatted = GameFormatter.format_date(game_date)
            user_name = UserFormatter.get_display_name(user)

            result["success"] = True
            result["message"] = f"✅ Вы удалены из {date_formatted}"

            # Обновить напоминание через reminder_system
            updated_game = await self.db.get_game_by_date(game_date)
            if updated_game and updated_game.time and len(updated_game.get_players()) > 0 and self.reminder_system:
                try:
                    await self.reminder_system.schedule_reminder(game_date.date(), updated_game.time)
                    logger.debug(f"Напоминание обновлено для игры {date_formatted}")
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"Ошибка обновления напоминания: {e}")

            # Отправить уведомление
            if self.config.notification_enabled:
                notification_message = (
                    f"⚠️ <b>Игрок удалился</b>\n\n"
                    f"{user_name} удалился/-лась из игры <b>{date_formatted}</b>\n\n"
                    f"🔓 Освободилось место!"
                )
                await NotificationService.send_to_all_users(
                    self.bot, self.db, notification_message, exclude_user_id=user.id,
                )
        else:
            result["message"] = "❌ Ошибка удаления"

        return result


class GameListHandler:
    """Обработчик списков игр."""

    def __init__(self, game_service: GameService, config: BotConfig | None = None) -> None:  # noqa: D107
        self.game_service = game_service
        self.config = config or BotConfig()

    async def show_available_games(
            self,
            message_or_callback: Message | CallbackQuery,
            page: int = 0,
            edit: bool = True,  # noqa: FBT001, FBT002
    ) -> None:
        """Показать все игры."""
        offset = page * self.config.games_per_page

        games = await self.game_service.db.get_upcoming_games(
            limit=self.config.games_per_page,
            offset=offset,
        )
        total_count = await self.game_service.db.count_upcoming_games()
        total_pages = (total_count + self.config.games_per_page - 1) // self.config.games_per_page

        if not games:
            text = "🚫 Нет созданных игр"
        else:
            users_info = await self.game_service.get_users_for_games(games)
            text = "🟢 <b>Все игры</b>\n\n" + await GameFormatter.format_games_list(
                games, users_info,
            )

        # Дополнительные кнопки
        additional_buttons = [
            [
                InlineKeyboardButton(text="📝 Записаться", callback_data="register_menu_0"),
                InlineKeyboardButton(text="👤 Мои игры", callback_data="show_my_games_0"),
            ],
        ]

        keyboard = KeyboardBuilder.create_games_list_keyboard(
            "show_available_games", page, total_pages, additional_buttons,
        )

        await self._send_or_edit_message(message_or_callback, text, keyboard, edit)

    async def show_my_games(
            self,
            message_or_callback: Message | CallbackQuery,
            user_id: int,
            page: int = 0,
            edit: bool = True,  # noqa: FBT001, FBT002
    ) -> None:
        """Показать игры пользователя."""
        offset = page * self.config.games_per_page

        games = await self.game_service.db.get_user_games(
            user_id,
            limit=self.config.games_per_page,
            offset=offset,
        )
        total_count = await self.game_service.db.count_user_games(user_id)
        total_pages = (total_count + self.config.games_per_page - 1) // self.config.games_per_page

        if not games:
            text = "👤 <b>Мои игры</b>\n\n🚫 Вы не записаны ни на одну игру"
        else:
            users_info = await self.game_service.get_users_for_games(games)
            text = "👤 <b>Мои игры</b>\n\n" + await GameFormatter.format_games_list(
                games, users_info,
            )

        # Дополнительные кнопки
        additional_buttons = [
            [
                InlineKeyboardButton(text="❌ Удалиться", callback_data="unregister_menu_0"),
                InlineKeyboardButton(text="🟢 Все игры", callback_data="show_available_games_0"),
            ],
        ]

        keyboard = KeyboardBuilder.create_games_list_keyboard(
            "show_my_games", page, total_pages, additional_buttons,
        )

        await self._send_or_edit_message(message_or_callback, text, keyboard, edit)

    @staticmethod
    async def _send_or_edit_message(
            message_or_callback: Message | CallbackQuery,
            text: str,
            keyboard: InlineKeyboardMarkup,
            edit: bool,  # noqa: FBT001
    ) -> None:
        """Отправить или редактировать сообщение."""
        if edit and hasattr(message_or_callback, "message"):
            await message_or_callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        else:
            await message_or_callback.answer(text, reply_markup=keyboard, parse_mode="HTML")
