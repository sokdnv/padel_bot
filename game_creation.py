import logging
from datetime import datetime, time

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from database import Database
from handlers import get_user_display_name, send_notification_to_all_users

logger = logging.getLogger(__name__)
router = Router()


class GameCreation(StatesGroup):
    waiting_for_date = State()
    waiting_for_time = State()
    waiting_for_duration = State()
    waiting_for_location = State()
    waiting_for_court = State()


def create_game_management_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура управления играми"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Создать игру", callback_data="create_game")],
            [InlineKeyboardButton(text="🗑 Удаление игры", callback_data="my_created_games_0")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")],
        ]
    )
    return keyboard


async def create_my_games_keyboard(db: Database, user_id: int, page: int = 0) -> InlineKeyboardMarkup:
    """Клавиатура с созданными пользователем играми"""
    GAMES_PER_PAGE = 4
    offset = page * GAMES_PER_PAGE

    games = await db.get_created_games(user_id, limit=GAMES_PER_PAGE, offset=offset)
    total_count = await db.count_created_games(user_id)
    total_pages = (total_count + GAMES_PER_PAGE - 1) // GAMES_PER_PAGE

    keyboard = []

    # Добавляем кнопки с играми
    for game in games:
        date_str = game.date.strftime("%d.%m")
        time_str = f" в {game.time}" if game.time else ""
        button_text = f"🗑 {date_str}{time_str}"
        callback_data = f"delete_game_{game.date.strftime('%Y-%m-%d')}"
        keyboard.append([InlineKeyboardButton(text=button_text, callback_data=callback_data)])

    # Навигация
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"my_created_games_{page - 1}"))

    if total_pages > 1:
        nav_buttons.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="current_page"))

    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"my_created_games_{page + 1}"))

    if nav_buttons:
        keyboard.append(nav_buttons)

    keyboard.append([InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


@router.callback_query(F.data == "game_management")
async def game_management_menu(callback: CallbackQuery):
    """Меню управления играми"""
    text = "🎮 <b>Управление играми</b>\n\nВыберите действие:"
    await callback.message.edit_text(text, reply_markup=create_game_management_keyboard(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "create_game")
async def start_game_creation(callback: CallbackQuery, state: FSMContext):
    """Начало создания игры"""
    text = (
        "📅 <b>Создание новой игры</b>\n\n"
        "Введите дату игры в формате ДД.ММ.ГГГГ или ДД.ММ\n"
        "Например: 25.12.2024 или 25.12"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="back_to_main")]]
    )

    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await state.set_state(GameCreation.waiting_for_date)
    await callback.answer()


@router.message(GameCreation.waiting_for_date)
async def process_date(message: Message, state: FSMContext):
    """Обработка ввода даты"""
    try:
        date_text = message.text.strip()

        # Парсинг даты
        if len(date_text.split('.')) == 2:  # Формат ДД.ММ
            day, month = date_text.split('.')
            year = datetime.now().year
            if int(month) < datetime.now().month:
                year += 1
            date_str = f"{day}.{month}.{year}"
        else:  # Формат ДД.ММ.ГГГГ
            date_str = date_text

        game_date = datetime.strptime(date_str, "%d.%m.%Y")

        # Проверка, что дата не в прошлом
        if game_date.date() < datetime.now().date():
            await message.answer("❌ Дата не может быть в прошлом. Попробуйте снова:")
            return

        await state.update_data(date=game_date)

        text = (
            "🕐 <b>Время игры</b>\n\n"
            "Введите время начала игры в формате ЧЧ:ММ\n"
            "Например: 19:30"
        )

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="back_to_main")]]
        )

        await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
        await state.set_state(GameCreation.waiting_for_time)

    except ValueError:
        await message.answer("❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ или ДД.ММ")


@router.message(GameCreation.waiting_for_time)
async def process_time(message: Message, state: FSMContext):
    """Обработка ввода времени"""
    try:
        time_str = message.text.strip()
        game_time = datetime.strptime(time_str, "%H:%M").time()

        await state.update_data(time=game_time)

        text = (
            "⏱ <b>Продолжительность игры</b>\n\n"
            "Введите продолжительность в минутах (от 60 до 180):"
        )

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="back_to_main")]]
        )

        await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
        await state.set_state(GameCreation.waiting_for_duration)

    except ValueError:
        await message.answer("❌ Неверный формат времени. Используйте ЧЧ:ММ (например: 19:30)")


@router.message(GameCreation.waiting_for_duration)
async def process_duration(message: Message, state: FSMContext):
    """Обработка ввода продолжительности"""
    try:
        duration = int(message.text.strip())

        if duration < 60 or duration > 180:
            await message.answer("❌ Продолжительность должна быть от 60 до 180 минут. Попробуйте снова:")
            return

        await state.update_data(duration=duration)

        text = (
            "📍 <b>Локация</b>\n\n"
            "Введите адрес или название места проведения игры:"
        )

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="back_to_main")]]
        )

        await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
        await state.set_state(GameCreation.waiting_for_location)

    except ValueError:
        await message.answer("❌ Введите число от 60 до 180")


@router.callback_query(F.data.startswith("duration_"))
async def process_duration(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора продолжительности"""
    duration = int(callback.data.split("_")[1])
    await state.update_data(duration=duration)

    text = (
        "📍 <b>Локация</b>\n\n"
        "Введите адрес или название места проведения игры:"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="back_to_main")]]
    )

    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await state.set_state(GameCreation.waiting_for_location)
    await callback.answer()


@router.message(GameCreation.waiting_for_location)
async def process_location(message: Message, state: FSMContext):
    """Обработка ввода локации"""
    location = message.text.strip()
    await state.update_data(location=location)

    text = (
        "🎾 <b>Номер корта</b>\n\n"
        "Введите номер корта"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="back_to_main")]]
    )

    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    await state.set_state(GameCreation.waiting_for_court)


@router.message(GameCreation.waiting_for_court)
async def process_court(message: Message, state: FSMContext, db: Database, bot):
    """Обработка ввода номера корта и создание игры"""
    try:
        court = int(message.text.strip())
        data = await state.get_data()

        # Создание игры
        success = await db.create_game(
            date=data['date'],
            time=data['time'],
            duration=data['duration'],
            location=data['location'],
            court=court,
            admin=message.from_user.id
        )

        if success:
            # Автоматически записать создателя на игру
            await db.register_player(data['date'], message.from_user.id)

            # Запланировать напоминание
            from scheduler import schedule_reminder
            await schedule_reminder(data['date'].date(), data['time'])

            date_str = data['date'].strftime("%d.%m.%Y")
            time_str = data['time'].strftime("%H:%M")
            duration_hours = data['duration'] // 60
            duration_minutes = data['duration'] % 60
            duration_str = f"{duration_hours}ч" + (f" {duration_minutes}м" if duration_minutes else "")

            creator_name = get_user_display_name(message.from_user)

            # Уведомление создателю
            success_text = (
                f"✅ <b>Игра создана!</b>\n\n"
                f"📅 Дата: {date_str}\n"
                f"🕐 Время: {time_str}\n"
                f"⏱ Продолжительность: {duration_str}\n"
                f"📍 Локация: {data['location']}\n"
                f"🎾 Корт: №{court}\n\n"
            )

            from handlers import create_main_keyboard
            await message.answer(success_text, reply_markup=create_main_keyboard(), parse_mode="HTML")

            # Уведомление всем пользователям
            notification_text = (
                f"🆕 <b>Новая игра создана!</b>\n\n"
                f"👤 Создатель: {creator_name}\n"
                f"📅 Дата: {date_str}\n"
                f"🕐 Время: {time_str}\n"
                f"⏱ Продолжительность: {duration_str}\n"
                f"📍 Локация: {data['location']}\n"
                f"🎾 Корт: №{court}\n\n"
            )

            await send_notification_to_all_users(bot, db, notification_text, exclude_user_id=message.from_user.id)

        else:
            await message.answer("❌ Ошибка создания игры. Возможно, игра на эту дату уже существует.")

        await state.clear()

    except ValueError:
        await message.answer("❌ Номер корта должен быть числом. Попробуйте снова:")


@router.callback_query(F.data.startswith("my_created_games_"))
async def show_my_created_games(callback: CallbackQuery, db: Database):
    """Показать созданные пользователем игры"""
    page = int(callback.data.split("_")[-1])

    games = await db.get_created_games(callback.from_user.id, limit=4, offset=page * 4)

    text = "🚫 Вы не создавали игр" if not games else "🗑 <b>Мои созданные игры</b>\n\nВыберите игру для удаления:\n\n"

    keyboard = await create_my_games_keyboard(db, callback.from_user.id, page)
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("delete_game_"))
async def delete_game(callback: CallbackQuery, db: Database, bot):
    """Удаление игры"""
    date_str = callback.data.split("_")[2]
    date = datetime.strptime(date_str, "%Y-%m-%d")

    # Проверяем, что пользователь - создатель игры
    game = await db.get_game_by_date(date)
    if not game:
        await callback.answer("❌ Игра не найдена", show_alert=True)
        return

    logger.info(f"Игра найдена: admin={game.admin}, user_id={callback.from_user.id}")

    if game.admin != callback.from_user.id:
        await callback.answer("❌ Вы можете удалять только свои игры", show_alert=True)
        return

    # Получаем список записанных игроков для уведомления
    players = game.get_players()

    # Удаляем игру
    success = await db.delete_game(date, callback.from_user.id)

    if success:
        date_formatted = date.strftime("%d.%m.%Y")
        creator_name = get_user_display_name(callback.from_user)

        await callback.answer(f"✅ Игра на {date_formatted} удалена", show_alert=True)

        # Уведомляем записанных игроков
        if players:
            notification_text = (
                f"❌ <b>Игра отменена</b>\n\n"
                f"Создатель {creator_name} отменил игру на <b>{date_formatted}</b>\n"
                f"Извините за неудобства!"
            )

            for player_id in players:
                if player_id != callback.from_user.id:
                    try:
                        await bot.send_message(player_id, notification_text, parse_mode="HTML")
                    except Exception as e:
                        logger.warning(f"Не удалось уведомить игрока {player_id}: {e}")

        # Возвращаемся в главное меню
        from handlers import create_main_keyboard
        text = "🎾 <b>Добро пожаловать в бот записи на падел!</b>\n\nЧто хотите сделать?"
        await callback.message.edit_text(text, reply_markup=create_main_keyboard(), parse_mode="HTML")
    else:
        await callback.answer("❌ Ошибка удаления игры", show_alert=True)
