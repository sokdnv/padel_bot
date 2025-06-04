import logging
from datetime import datetime

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from database import Database
from scheduler import schedule_reminder

logger = logging.getLogger(__name__)
router = Router()


async def send_notification_to_all_users(bot, db: Database, message: str, exclude_user_id: int = None):
    """Отправить уведомление всем пользователям"""
    try:
        all_users = await db.get_all_users()
        for user_id in all_users:
            if exclude_user_id and user_id == exclude_user_id:
                continue  # Не отправляем уведомление самому пользователю

            try:
                await bot.send_message(user_id, message, parse_mode="HTML")
            except Exception as e:
                # Пользователь заблокировал бота или удалил аккаунт
                logger.warning(f"Не удалось отправить уведомление пользователю {user_id}: {e}")
                continue

    except Exception as e:
        logger.error(f"Ошибка при отправке уведомлений: {e}")


def get_user_display_name(user) -> str:
    """Получить отображаемое имя пользователя"""
    if user.username:
        return f"@{user.username}"
    if user.first_name:
        return user.first_name
    return f"User{user.id}"


async def format_games_list(db: Database, games: list, users_info: dict = None) -> str:
    """Форматировать список игр для отображения"""
    if not games:
        return "🚫 Нет доступных игр"
    text = ""
    for game in games:
        date_str = game.date.strftime("%d.%m.%Y")
        players_count = len(game.get_players())
        free_slots = game.free_slots()
        status_emoji = "🔍" if free_slots > 0 else "✅"
        # Формируем время и длительность
        time_info = ""
        if game.time:
            time_info = f"{game.time}"
            if game.duration:
                hours = game.duration // 60
                minutes = game.duration % 60
                if minutes == 0:
                    time_info += f" ({hours}ч)"
                else:
                    time_info += f" ({hours}ч {minutes}м)"
        text += f"{status_emoji} <b>{date_str}</b>  "
        if time_info:
            text += f"{time_info}\n"
        if game.location:
            text += f"📍 {game.location}\n"
        text += f"📊 Занято: {players_count}/4\n"
        if players_count > 0 and users_info:
            text += "👥 Записаны: "
            player_names = []
            for player_id in game.get_players():
                if player_id in users_info:
                    player_names.append(users_info[player_id])
                else:
                    player_names.append(f"User{player_id}")
            text += ", ".join(player_names) + "\n"
        elif players_count > 0:
            text += f"👥 Записаны: {players_count} игрок(ов)\n"
        text += "\n"
    return text


def create_main_keyboard() -> InlineKeyboardMarkup:
    """Создать главную клавиатуру"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🟢 Свободные игры", callback_data="show_available_games_0")],
            [InlineKeyboardButton(text="👤 Мои игры", callback_data="show_my_games_0")],
            [InlineKeyboardButton(text="📝 Записаться", callback_data="register_menu_0")],
            [InlineKeyboardButton(text="❌ Удалиться из игры", callback_data="unregister_menu_0")],
        ],
    )
    return keyboard


def create_pagination_keyboard(
    action: str,
    page: int,
    total_pages: int,
    has_next: bool = False,
    has_prev: bool = False,
) -> InlineKeyboardMarkup:
    """Создать клавиатуру с пагинацией"""
    keyboard = []

    # Кнопки навигации
    nav_buttons = []
    if has_prev:
        nav_buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"{action}_{page - 1}"))

    if total_pages > 1:
        nav_buttons.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="current_page"))

    if has_next:
        nav_buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"{action}_{page + 1}"))

    if nav_buttons:
        keyboard.append(nav_buttons)

    # Кнопка "Назад в меню"
    keyboard.append([InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")])


async def create_date_selection_keyboard(
    db: Database,
    action: str,
    user_id: int = None,
    page: int = 0,
) -> InlineKeyboardMarkup:
    """Создать клавиатуру выбора даты с пагинацией"""
    GAMES_PER_PAGE = 4
    offset = page * GAMES_PER_PAGE

    if action == "register":
        games = await db.get_available_games(limit=GAMES_PER_PAGE, offset=offset, exclude_user_id=user_id)
        total_count = (
            await db.count_available_games_excluding_user(user_id) if user_id else await db.count_available_games()
        )
    elif action == "unregister" and user_id:
        games = await db.get_user_games(user_id, limit=GAMES_PER_PAGE, offset=offset)
        total_count = await db.count_user_games(user_id)
    else:
        return InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")]],
        )

    keyboard = []

    # Добавляем кнопки с играми
    for game in games:
        date_str = game.date.strftime("%d.%m")

        if action == "register":
            free_slots = game.free_slots()
            text = f"{date_str} (свободно: {free_slots})"
            callback_data = f"register_{game.date.strftime('%Y-%m-%d')}"
        else:  # unregister
            text = f"{date_str}"
            callback_data = f"unregister_{game.date.strftime('%Y-%m-%d')}"

        keyboard.append([InlineKeyboardButton(text=text, callback_data=callback_data)])

    # Добавляем навигацию
    total_pages = (total_count + GAMES_PER_PAGE - 1) // GAMES_PER_PAGE
    has_prev = page > 0
    has_next = page < total_pages - 1

    nav_buttons = []
    if has_prev:
        nav_buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"{action}_menu_{page - 1}"))

    if total_pages > 1:
        nav_buttons.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="current_page"))

    if has_next:
        nav_buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"{action}_menu_{page + 1}"))

    if nav_buttons:
        keyboard.append(nav_buttons)

    keyboard.append([InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


@router.message(Command("start"))
async def start_command(message: Message, db: Database, bot):
    """Обработчик команды /start"""
    await db.save_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.first_name,
        message.from_user.last_name,
    )

    text = "🎾 <b>Добро пожаловать в бот записи на падел!</b>\n\nЧто хотите сделать?"

    await message.answer(text, reply_markup=create_main_keyboard(), parse_mode="HTML")


@router.message(Command("games"))
async def games_command(message: Message, db: Database, bot):
    """Обработчик команды /games"""
    await show_available_games(message, db, page=0, edit=False)


async def show_available_games(message_or_callback, db: Database, page: int = 0, edit: bool = True):
    """Показать свободные игры"""
    GAMES_PER_PAGE = 4
    offset = page * GAMES_PER_PAGE

    games = await db.get_available_games(limit=GAMES_PER_PAGE, offset=offset)
    total_count = await db.count_available_games()
    total_pages = (total_count + GAMES_PER_PAGE - 1) // GAMES_PER_PAGE

    if not games:
        text = "🚫 Нет свободных игр"
    else:
        # Получаем информацию о пользователях
        all_player_ids = []
        for game in games:
            all_player_ids.extend(game.get_players())

        users_info = await db.get_users_info(list(set(all_player_ids))) if all_player_ids else {}

        text = "🟢 <b>Свободные игры</b>\n\n" + await format_games_list(db, games, users_info)

    # Создаем клавиатуру
    keyboard = []

    # Кнопки навигации
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"show_available_games_{page - 1}"))

    if total_pages > 1:
        nav_buttons.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="current_page"))

    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"show_available_games_{page + 1}"))

    if nav_buttons:
        keyboard.append(nav_buttons)

    # Кнопки действий
    keyboard.append(
        [
            InlineKeyboardButton(text="📝 Записаться", callback_data="register_menu_0"),
            InlineKeyboardButton(text="👤 Мои игры", callback_data="show_my_games_0"),
        ],
    )

    # Кнопка "Главное меню"
    keyboard.append([InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")])

    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)

    if edit and hasattr(message_or_callback, "message"):
        await message_or_callback.message.edit_text(text, reply_markup=reply_markup, parse_mode="HTML")
    else:
        await message_or_callback.answer(text, reply_markup=reply_markup, parse_mode="HTML")


async def show_my_games(message_or_callback, db: Database, user_id: int, page: int = 0, edit: bool = True):
    """Показать игры пользователя"""
    GAMES_PER_PAGE = 4
    offset = page * GAMES_PER_PAGE

    games = await db.get_user_games(user_id, limit=GAMES_PER_PAGE, offset=offset)
    total_count = await db.count_user_games(user_id)
    total_pages = (total_count + GAMES_PER_PAGE - 1) // GAMES_PER_PAGE

    if not games:
        text = "👤 <b>Мои игры</b>\n\n🚫 Вы не записаны ни на одну игру"
    else:
        # Получаем информацию о пользователях
        all_player_ids = []
        for game in games:
            all_player_ids.extend(game.get_players())

        users_info = await db.get_users_info(list(set(all_player_ids))) if all_player_ids else {}

        text = "👤 <b>Мои игры</b>\n\n" + await format_games_list(db, games, users_info)

    # Создаем клавиатуру
    keyboard = []

    # Кнопки навигации
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"show_my_games_{page - 1}"))

    if total_pages > 1:
        nav_buttons.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="current_page"))

    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"show_my_games_{page + 1}"))

    if nav_buttons:
        keyboard.append(nav_buttons)

    # Кнопки действий
    keyboard.append(
        [
            InlineKeyboardButton(text="❌ Удалиться из игры", callback_data="unregister_menu_0"),
            InlineKeyboardButton(text="🟢 Свободные игры", callback_data="show_available_games_0"),
        ],
    )

    # Кнопка "Главное меню"
    keyboard.append([InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")])

    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)

    if edit and hasattr(message_or_callback, "message"):
        await message_or_callback.message.edit_text(text, reply_markup=reply_markup, parse_mode="HTML")
    else:
        await message_or_callback.answer(text, reply_markup=reply_markup, parse_mode="HTML")


@router.callback_query(F.data.startswith("show_available_games_"))
async def show_available_games_callback(callback: CallbackQuery, db: Database, bot):
    """Показать свободные игры"""
    page = int(callback.data.split("_")[-1])
    await show_available_games(callback, db, page=page, edit=True)
    await callback.answer()


@router.callback_query(F.data.startswith("show_my_games_"))
async def show_my_games_callback(callback: CallbackQuery, db: Database, bot):
    """Показать мои игры"""
    page = int(callback.data.split("_")[-1])
    await show_my_games(callback, db, callback.from_user.id, page=page, edit=True)
    await callback.answer()


@router.callback_query(F.data.startswith("register_menu_"))
async def register_menu_callback(callback: CallbackQuery, db: Database, bot):
    """Меню записи на игру"""
    page = int(callback.data.split("_")[-1])
    keyboard = await create_date_selection_keyboard(db, "register", user_id=callback.from_user.id, page=page)
    text = "📝 <b>Выберите дату для записи:</b>\n\n"

    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("unregister_menu_"))
async def unregister_menu_callback(callback: CallbackQuery, db: Database, bot):
    """Меню отписки от игры"""
    page = int(callback.data.split("_")[-1])
    keyboard = await create_date_selection_keyboard(db, "unregister", user_id=callback.from_user.id, page=page)
    text = "❌ <b>Выберите дату:</b>\n\n"

    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("register_"))
async def register_player_callback(callback: CallbackQuery, db: Database, bot):
    """Записать игрока на игру"""
    if callback.data.startswith("register_menu_"):
        return  # Это вызов меню, не регистрация

    date_str = callback.data.split("_")[1]
    date = datetime.strptime(date_str, "%Y-%m-%d")
    user_id = callback.from_user.id

    # Проверить, можно ли записаться
    game = await db.get_game_by_date(date)
    if not game:
        await callback.answer("❌ Игра не найдена", show_alert=True)
        return

    if game.has_player(user_id):
        await callback.answer("⚠️ Вы уже записаны на эту игру", show_alert=True)
        return

    if game.is_full():
        await callback.answer("❌ Нет свободных мест", show_alert=True)
        return

    # Записать игрока
    success = await db.register_player(date, user_id)
    if success:
        date_formatted = date.strftime("%d.%m.%Y")
        user_name = get_user_display_name(callback.from_user)

        await callback.answer(f"✅ Вы записаны на {date_formatted}", show_alert=True)

        updated_game = await db.get_game_by_date(date)
        if updated_game and updated_game.time:
            await schedule_reminder(date.date(), updated_game.time)

        # Отправить уведомление всем пользователям
        notification_message = f"🎾 <b>Новая запись на игру!</b>\n\n{user_name} записался на <b>{date_formatted}</b>"
        await send_notification_to_all_users(bot, db, notification_message, exclude_user_id=user_id)

        # Вернуться в главное меню
        text = "🎾 <b>Добро пожаловать в бот записи на падел!</b>\n\nЧто хотите сделать?"
        await callback.message.edit_text(text, reply_markup=create_main_keyboard(), parse_mode="HTML")
    else:
        await callback.answer("❌ Ошибка записи", show_alert=True)


@router.callback_query(F.data.startswith("unregister_"))
async def unregister_player_callback(callback: CallbackQuery, db: Database, bot):
    """Отписать игрока от игры"""
    if callback.data.startswith("unregister_menu_"):
        return  # Это вызов меню, не отписка

    date_str = callback.data.split("_")[1]
    date = datetime.strptime(date_str, "%Y-%m-%d")
    user_id = callback.from_user.id

    # Проверить, записан ли игрок
    game = await db.get_game_by_date(date)
    if not game:
        await callback.answer("❌ Игра не найдена", show_alert=True)
        return

    if not game.has_player(user_id):
        await callback.answer("⚠️ Вы не записаны на эту игру", show_alert=True)
        return

    # Отписать игрока
    success = await db.unregister_player(date, user_id)
    if success:
        date_formatted = date.strftime("%d.%m.%Y")
        user_name = get_user_display_name(callback.from_user)

        await callback.answer(f"✅ Вы удалены из {date_formatted}", show_alert=True)

        updated_game = await db.get_game_by_date(date)
        if updated_game and updated_game.time and len(updated_game.get_players()) > 0:
            await schedule_reminder(date.date(), updated_game.time)

        # Отправить уведомление всем пользователям
        notification_message = (
            f"⚠️ <b>Игрок удалился</b>\n\n{user_name} удалился из игры <b>{date_formatted}</b>\n\n🔓 Освободилось место!"
        )
        await send_notification_to_all_users(bot, db, notification_message, exclude_user_id=user_id)

        # Вернуться в главное меню
        text = "🎾 <b>Добро пожаловать в бот записи на падел!</b>\n\nЧто хотите сделать?"
        await callback.message.edit_text(text, reply_markup=create_main_keyboard(), parse_mode="HTML")
    else:
        await callback.answer("❌ Ошибка удаления", show_alert=True)


@router.callback_query(F.data == "back_to_main")
async def back_to_main_callback(callback: CallbackQuery, bot):
    """Вернуться в главное меню"""
    text = "🎾 <b>Добро пожаловать в бот записи на падел!</b>\n\nЧто хотите сделать?"
    await callback.message.edit_text(text, reply_markup=create_main_keyboard(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "current_page")
async def current_page_callback(callback: CallbackQuery, bot):
    """Заглушка для кнопки текущей страницы"""
    await callback.answer()
