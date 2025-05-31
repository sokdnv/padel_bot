from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from datetime import datetime
import logging

from database import Database

logger = logging.getLogger(__name__)
router = Router()

def get_user_display_name(user) -> str:
    """Получить отображаемое имя пользователя"""
    if user.username:
        return f"@{user.username}"
    elif user.first_name:
        return user.first_name
    else:
        return f"User{user.id}"

async def format_games_list(db: Database) -> str:
    """Форматировать список игр для отображения"""
    games = await db.get_upcoming_games()
    
    if not games:
        return "🚫 Нет доступных игр"
    
    text = "🎾 <b>Игры на падел (Четверги 15:00-17:00)</b>\n\n"
    
    for game in games:
        date_str = game.date.strftime("%d.%m.%Y")
        players_count = len(game.get_players())
        free_slots = game.free_slots()
        
        status_emoji = "✅" if free_slots > 0 else "❌"
        
        text += f"{status_emoji} <b>{date_str}</b>\n"
        text += f"📊 Занято: {players_count}/4 | Свободно: {free_slots}\n"
        
        if players_count > 0:
            text += "👥 Записаны: "
            # В реальном приложении здесь бы отображались имена игроков
            # Для простоты показываем количество
            text += f"{players_count} игрок(ов)\n"
        
        text += "\n"
    
    return text

def create_games_keyboard() -> InlineKeyboardMarkup:
    """Создать клавиатуру с играми"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 Показать игры", callback_data="show_games")],
        [InlineKeyboardButton(text="📝 Записаться", callback_data="register_menu")],
        [InlineKeyboardButton(text="❌ Отписаться", callback_data="unregister_menu")]
    ])
    return keyboard

async def create_date_selection_keyboard(db: Database, action: str) -> InlineKeyboardMarkup:
    """Создать клавиатуру выбора даты"""
    games = await db.get_upcoming_games()
    keyboard = []
    
    for game in games:
        date_str = game.date.strftime("%d.%m")
        free_slots = game.free_slots()
        
        if action == "register" and free_slots > 0:
            text = f"{date_str} (свободно: {free_slots})"
            callback_data = f"register_{game.date.strftime('%Y-%m-%d')}"
            keyboard.append([InlineKeyboardButton(text=text, callback_data=callback_data)])
        elif action == "unregister":
            text = f"{date_str}"
            callback_data = f"unregister_{game.date.strftime('%Y-%m-%d')}"
            keyboard.append([InlineKeyboardButton(text=text, callback_data=callback_data)])
    
    keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

@router.message(Command("start"))
async def start_command(message: Message, db: Database):
    """Обработчик команды /start"""
    await db.save_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.first_name,
        message.from_user.last_name
    )
    
    text = (
        "🎾 <b>Добро пожаловать в бот записи на падел!</b>\n\n"
        "Мы играем каждый четверг с 15:00 до 17:00\n"
        "Максимум 4 игрока на корт\n\n"
        "Что хотите сделать?"
    )
    
    await message.answer(text, reply_markup=create_games_keyboard(), parse_mode="HTML")

@router.message(Command("games"))
async def games_command(message: Message, db: Database):
    """Обработчик команды /games"""
    text = await format_games_list(db)
    await message.answer(text, reply_markup=create_games_keyboard(), parse_mode="HTML")

@router.callback_query(F.data == "show_games")
async def show_games_callback(callback: CallbackQuery, db: Database):
    """Показать список игр"""
    text = await format_games_list(db)
    await callback.message.edit_text(text, reply_markup=create_games_keyboard(), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "register_menu")
async def register_menu_callback(callback: CallbackQuery, db: Database):
    """Меню записи на игру"""
    keyboard = await create_date_selection_keyboard(db, "register")
    text = "📝 <b>Выберите дату для записи:</b>\n\nДоступны только даты со свободными местами"
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "unregister_menu")
async def unregister_menu_callback(callback: CallbackQuery, db: Database):
    """Меню отписки от игры"""
    keyboard = await create_date_selection_keyboard(db, "unregister")
    text = "❌ <b>Выберите дату для отписки:</b>"
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("register_"))
async def register_player_callback(callback: CallbackQuery, db: Database):
    """Записать игрока на игру"""
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
        user_name = get_user_display_name(callback.from_user)
        date_formatted = date.strftime("%d.%m.%Y")
        await callback.answer(f"✅ Вы записаны на {date_formatted}", show_alert=True)
        
        # Обновить отображение
        text = await format_games_list(db)
        await callback.message.edit_text(text, reply_markup=create_games_keyboard(), parse_mode="HTML")
    else:
        await callback.answer("❌ Ошибка записи", show_alert=True)

@router.callback_query(F.data.startswith("unregister_"))
async def unregister_player_callback(callback: CallbackQuery, db: Database):
    """Отписать игрока от игры"""
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
        await callback.answer(f"✅ Вы отписаны от {date_formatted}", show_alert=True)
        
        # Обновить отображение
        text = await format_games_list(db)
        await callback.message.edit_text(text, reply_markup=create_games_keyboard(), parse_mode="HTML")
    else:
        await callback.answer("❌ Ошибка отписки", show_alert=True)

@router.callback_query(F.data == "back_to_main")
async def back_to_main_callback(callback: CallbackQuery, db: Database):
    """Вернуться в главное меню"""
    text = await format_games_list(db)
    await callback.message.edit_text(text, reply_markup=create_games_keyboard(), parse_mode="HTML")
    await callback.answer()

