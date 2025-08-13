"""Общие клавиатуры и UI компоненты."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.database.db import Database


class CommonKeyboards:
    """Общие переиспользуемые клавиатуры."""

    @staticmethod
    def create_main_keyboard() -> InlineKeyboardMarkup:
        """Создать главную клавиатуру."""
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🟢 Все игры", callback_data="show_available_games_0")],
                [InlineKeyboardButton(text="👤 Мои записи", callback_data="show_my_games_0")],
                [InlineKeyboardButton(text="📝 Записаться", callback_data="register_menu_0")],
                [InlineKeyboardButton(text="❌ Удалиться", callback_data="unregister_menu_0")],
                [InlineKeyboardButton(text="🎮 Управление играми", callback_data="game_management")],
            ]
        )

    @staticmethod
    def create_back_to_main_button() -> list[InlineKeyboardButton]:
        """Кнопка возврата в главное меню."""
        return [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")]

    @staticmethod
    def create_cancel_keyboard() -> InlineKeyboardMarkup:
        """Клавиатура с кнопкой отмены."""
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отмена", callback_data="back_to_main")],
            ]
        )

    @staticmethod
    def create_delete_keyboard() -> InlineKeyboardMarkup:
        """Клавиатура с кнопкой удаления уведомления."""
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🗑 Удалить уведомление", callback_data="delete_message")],
            ]
        )


class PaginationHelper:
    """Помощник для создания пагинации."""

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
    def create_paginated_keyboard(
        action: str,
        page: int,
        total_pages: int,
        additional_buttons: list[list[InlineKeyboardButton]] | None = None,
    ) -> InlineKeyboardMarkup:
        """Создать клавиатуру со стандартной пагинацией."""
        keyboard = []

        # Навигация
        nav_buttons = PaginationHelper.create_navigation_buttons(action, page, total_pages)
        if nav_buttons:
            keyboard.append(nav_buttons)

        # Дополнительные кнопки
        if additional_buttons:
            keyboard.extend(additional_buttons)

        # Главное меню
        keyboard.append(CommonKeyboards.create_back_to_main_button())

        return InlineKeyboardMarkup(inline_keyboard=keyboard)

    @staticmethod
    async def create_date_selection_keyboard(
        db: Database,
        action: str,
        user_id: int | None = None,
        page: int = 0,
        games_per_page: int = 4,
    ) -> InlineKeyboardMarkup:
        """Создать клавиатуру выбора даты с пагинацией."""
        offset = page * games_per_page

        # Получение игр в зависимости от действия
        if action == "register":
            games = await db.get_available_games(
                limit=games_per_page,
                offset=offset,
                exclude_user_id=user_id,
            )
            total_count = (
                await db.count_available_games_excluding_user(user_id) if user_id else await db.count_available_games()
            )
        elif action == "unregister" and user_id:
            games = await db.get_user_games(user_id, limit=games_per_page, offset=offset)
            total_count = await db.count_user_games(user_id)
        else:
            return InlineKeyboardMarkup(
                inline_keyboard=[
                    CommonKeyboards.create_back_to_main_button(),
                ]
            )

        keyboard = []

        # Кнопки с играми
        from src.shared.formatters import Formatters  # Избегаем циклического импорта

        for game in games:
            button_text = Formatters.format_short_date(game.date)

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
        total_pages = (total_count + games_per_page - 1) // games_per_page
        nav_buttons = PaginationHelper.create_navigation_buttons(f"{action}_menu", page, total_pages)
        if nav_buttons:
            keyboard.append(nav_buttons)

        keyboard.append(CommonKeyboards.create_back_to_main_button())

        return InlineKeyboardMarkup(inline_keyboard=keyboard)
