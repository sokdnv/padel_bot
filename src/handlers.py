"""Скрипт с телеграмм хэндлерами."""

from datetime import datetime

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from src.database.db import Database
from src.services.core import BotConfig, GameListHandler, GameService, KeyboardBuilder

router = Router()


# Глобальные сервисы (будут инициализированы при запуске)
game_service: GameService | None = None
game_list_handler: GameListHandler | None = None


def init_handlers(db: Database, bot: Bot, reminder_system=None, config: BotConfig | None = None) -> None:  # noqa: ANN001
    """Инициализировать обработчики."""
    global game_service, game_list_handler  # noqa: PLW0603
    game_service = GameService(db, bot, reminder_system, config)
    game_list_handler = GameListHandler(game_service, config)


# Обработчики команд
@router.message(Command("start"))
async def start_command(message: Message, db: Database) -> None:
    """Обработчик команды /start."""
    await db.save_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.first_name,
        message.from_user.last_name,
    )

    text = "🎾 <b>Добро пожаловать в бот записи на падел!</b>\n\nЧто хотите сделать?"
    await message.answer(text, reply_markup=KeyboardBuilder.create_main_keyboard(), parse_mode="HTML")


@router.message(Command("games"))
async def games_command(message: Message) -> None:
    """Обработчик команды /games."""
    await game_list_handler.show_available_games(message, page=0, edit=False)


# Обработчики callback'ов
@router.callback_query(F.data.startswith("show_available_games_"))
async def show_available_games_callback(callback: CallbackQuery) -> None:
    """Показать все игры."""
    page = int(callback.data.split("_")[-1])
    await game_list_handler.show_available_games(callback, page=page, edit=True)
    await callback.answer()


@router.callback_query(F.data.startswith("show_my_games_"))
async def show_my_games_callback(callback: CallbackQuery) -> None:
    """Показать мои игры."""
    page = int(callback.data.split("_")[-1])
    await game_list_handler.show_my_games(callback, callback.from_user.id, page=page, edit=True)
    await callback.answer()


@router.callback_query(F.data.startswith("register_menu_"))
async def register_menu_callback(callback: CallbackQuery, db: Database) -> None:
    """Меню записи на игру."""
    page = int(callback.data.split("_")[-1])
    keyboard = await KeyboardBuilder.create_date_selection_keyboard(
        db, "register", user_id=callback.from_user.id, page=page,
    )
    text = "📝 <b>Выберите дату для записи:</b>\n\n"

    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("unregister_menu_"))
async def unregister_menu_callback(callback: CallbackQuery, db: Database) -> None:
    """Меню отписки от игры."""
    page = int(callback.data.split("_")[-1])
    keyboard = await KeyboardBuilder.create_date_selection_keyboard(
        db, "unregister", user_id=callback.from_user.id, page=page,
    )
    text = "❌ <b>Выберите дату:</b>\n\n"

    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("register_"))
async def register_player_callback(callback: CallbackQuery) -> None:
    """Записать игрока на игру."""
    if callback.data.startswith("register_menu_"):
        return  # Это вызов меню, не регистрация

    date_str = callback.data.split("_")[1]
    date = datetime.strptime(date_str, "%Y-%m-%d")  # noqa: DTZ007

    result = await game_service.register_player(date, callback.from_user)
    await callback.answer(result["message"], show_alert=result["alert"])

    if result["success"]:
        # Вернуться в главное меню
        text = "🎾 <b>Добро пожаловать в бот записи на падел!</b>\n\nЧто хотите сделать?"
        await callback.message.edit_text(
            text,
            reply_markup=KeyboardBuilder.create_main_keyboard(),
            parse_mode="HTML",
        )


@router.callback_query(F.data.startswith("unregister_"))
async def unregister_player_callback(callback: CallbackQuery) -> None:
    """Отписать игрока от игры."""
    if callback.data.startswith("unregister_menu_"):
        return  # Это вызов меню, не отписка

    date_str = callback.data.split("_")[1]
    date = datetime.strptime(date_str, "%Y-%m-%d")  # noqa: DTZ007

    result = await game_service.unregister_player(date, callback.from_user)
    await callback.answer(result["message"], show_alert=result["alert"])

    if result["success"]:
        # Вернуться в главное меню
        text = "🎾 <b>Добро пожаловать в бот записи на падел!</b>\n\nЧто хотите сделать?"
        await callback.message.edit_text(
            text,
            reply_markup=KeyboardBuilder.create_main_keyboard(),
            parse_mode="HTML",
        )


@router.callback_query(F.data == "back_to_main")
async def back_to_main_callback(callback: CallbackQuery) -> None:
    """Вернуться в главное меню."""
    text = "🎾 <b>Добро пожаловать в бот записи на падел!</b>\n\nЧто хотите сделать?"
    await callback.message.edit_text(
        text,
        reply_markup=KeyboardBuilder.create_main_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "current_page")
async def current_page_callback(callback: CallbackQuery) -> None:
    """Заглушка для кнопки текущей страницы."""
    await callback.answer()


@router.callback_query(F.data == "delete_message")
async def delete_message_handler(callback: CallbackQuery) -> None:
    """Обработчик удаления сообщения."""
    try:
        await callback.message.delete()
        await callback.answer("Сообщение удалено", show_alert=False)
    except Exception:  # noqa: S110
        pass
