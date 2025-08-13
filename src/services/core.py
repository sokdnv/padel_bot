"""Классы для работы бота."""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from aiogram import Bot
from aiogram.types import CallbackQuery, Message, User

from src.config import logger
from src.database.db import Database
from src.shared.decorators import handle_service_errors
from src.shared.formatters import Formatters
from src.shared.keyboards import CommonKeyboards, PaginationHelper
from src.shared.responses import ServiceResponse


@dataclass
class BotConfig:
    """Конфигурация бота."""

    games_per_page: int = 4
    notification_enabled: bool = True


class NotificationService:
    """Сервис уведомлений."""

    @staticmethod
    async def _send_notifications_background(
        bot: Bot,
        db: Database,
        message: str,
        exclude_user_id: int | None = None,
    ) -> dict[str, int]:
        """Отправить уведомления в фоне."""
        stats = {"sent": 0, "failed": 0}

        try:
            all_users = await db.get_all_users()
            delete_keyboard = CommonKeyboards.create_delete_keyboard()

            for user_id in all_users:
                if exclude_user_id and user_id == exclude_user_id:
                    continue
                try:
                    await bot.send_message(
                        user_id,
                        message,
                        parse_mode="HTML",
                        reply_markup=delete_keyboard,
                    )
                    stats["sent"] += 1
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"Не удалось отправить уведомление пользователю {user_id}: {e}")
                    stats["failed"] += 1
            logger.info(f"Уведомления отправлены: {stats['sent']} успешно, {stats['failed']} неудачно")
        except Exception as e:  # noqa: BLE001
            logger.error(f"Ошибка при отправке уведомлений: {e}")
        return stats

    @staticmethod
    def send_to_all_users_async(
        bot: Bot,
        db: Database,
        message: str,
        exclude_user_id: int | None = None,
    ) -> None:
        """Запустить отправку уведомлений в фоне без блокировки."""
        asyncio.create_task(NotificationService._send_notifications_background(bot, db, message, exclude_user_id))

    @staticmethod
    async def _send_to_players_background(
        bot: Bot,
        message: str,
        player_ids: list[int],
    ) -> None:
        """Отправить уведомления конкретным игрокам в фоне."""
        for player_id in player_ids:
            try:
                await bot.send_message(
                    player_id,
                    message,
                    parse_mode="HTML",
                )
            except Exception as e:  # noqa: BLE001
                logger.warning(f"Не удалось уведомить игрока {player_id}: {e}")

    @staticmethod
    def send_to_players_async(
        bot: Bot,
        message: str,
        player_ids: list[int],
    ) -> None:
        """Запустить отправку уведомлений конкретным игрокам в фоне."""
        asyncio.create_task(NotificationService._send_to_players_background(bot, message, player_ids))

    @staticmethod
    async def send_to_all_users(
        bot: Bot,
        db: Database,
        message: str,
        exclude_user_id: int | None = None,
    ) -> dict[str, int]:
        """Отправить уведомление всем пользователям (синхронно)."""
        return await NotificationService._send_notifications_background(bot, db, message, exclude_user_id)


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

    @handle_service_errors("Ошибка регистрации")
    async def register_player(self, game_date: datetime, user: User) -> ServiceResponse:
        """Записать игрока на игру."""
        # Получить игру
        game = await self.db.get_game_by_date(game_date)
        if not game:
            return ServiceResponse.error_response("❌ Игра не найдена")

        if game.has_player(user.id):
            return ServiceResponse.error_response("⚠️ Вы уже записаны на эту игру")

        if game.is_full():
            return ServiceResponse.error_response("❌ Нет свободных мест")

        # Записать игрока
        success = await self.db.register_player(game_date, user.id)
        if success:
            date_formatted = Formatters.format_date(game_date)
            user_name = Formatters.get_display_name(user)

            # Запланировать напоминание через reminder_system
            updated_game = await self.db.get_game_by_date(game_date)
            if updated_game and updated_game.time and self.reminder_system:
                try:
                    await self.reminder_system.schedule_reminder(game_date.date(), updated_game.time)
                    logger.debug(f"Напоминание запланировано для игры {date_formatted}")
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"Ошибка планирования напоминания: {e}")

            # Отправить уведомление в фоне
            if self.config.notification_enabled:
                notification_message = (
                    f"🎾 <b>Новая запись на игру!</b>\n\n{user_name} записался/-лась на <b>{date_formatted}</b>"
                )
                NotificationService.send_to_all_users_async(
                    self.bot,
                    self.db,
                    notification_message,
                    exclude_user_id=user.id,
                )

            return ServiceResponse.success_response(f"✅ Вы записаны на {date_formatted}", alert=False)
        return ServiceResponse.error_response("❌ Ошибка записи")

    @handle_service_errors("Ошибка отмены регистрации")
    async def unregister_player(self, game_date: datetime, user: User) -> ServiceResponse:
        """Отписать игрока от игры."""
        # Получить игру
        game = await self.db.get_game_by_date(game_date)
        if not game:
            return ServiceResponse.error_response("❌ Игра не найдена")

        if not game.has_player(user.id):
            return ServiceResponse.error_response("⚠️ Вы не записаны на эту игру")

        # Отписать игрока
        success = await self.db.unregister_player(game_date, user.id)
        if success:
            date_formatted = Formatters.format_date(game_date)
            user_name = Formatters.get_display_name(user)

            # Обновить напоминание через reminder_system
            updated_game = await self.db.get_game_by_date(game_date)
            if updated_game and updated_game.time and len(updated_game.get_players()) > 0 and self.reminder_system:
                try:
                    await self.reminder_system.schedule_reminder(game_date.date(), updated_game.time)
                    logger.debug(f"Напоминание обновлено для игры {date_formatted}")
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"Ошибка обновления напоминания: {e}")

            # Отправить уведомление в фоне
            if self.config.notification_enabled:
                notification_message = (
                    f"⚠️ <b>Игрок удалился</b>\n\n"
                    f"{user_name} удалился/-лась из игры <b>{date_formatted}</b>\n\n"
                    f"🔓 Освободилось место!"
                )
                NotificationService.send_to_all_users_async(
                    self.bot,
                    self.db,
                    notification_message,
                    exclude_user_id=user.id,
                )

            return ServiceResponse.success_response(f"✅ Вы удалены из {date_formatted}", alert=False)
        return ServiceResponse.error_response("❌ Ошибка удаления")


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
            text = "🟢 <b>Все игры</b>\n\n" + await Formatters.format_games_list(
                games,
                users_info,
            )

        # Дополнительные кнопки
        from aiogram.types import InlineKeyboardButton  # Избегаем циклического импорта

        additional_buttons = [
            [
                InlineKeyboardButton(text="📝 Записаться", callback_data="register_menu_0"),
                InlineKeyboardButton(text="👤 Мои игры", callback_data="show_my_games_0"),
            ],
        ]

        keyboard = PaginationHelper.create_paginated_keyboard(
            "show_available_games",
            page,
            total_pages,
            additional_buttons,
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
            text = "👤 <b>Мои игры</b>\n\n" + await Formatters.format_games_list(
                games,
                users_info,
            )

        # Дополнительные кнопки
        from aiogram.types import InlineKeyboardButton  # Избегаем циклического импорта

        additional_buttons = [
            [
                InlineKeyboardButton(text="❌ Удалиться", callback_data="unregister_menu_0"),
                InlineKeyboardButton(text="🟢 Все игры", callback_data="show_available_games_0"),
            ],
        ]

        keyboard = PaginationHelper.create_paginated_keyboard(
            "show_my_games",
            page,
            total_pages,
            additional_buttons,
        )

        await self._send_or_edit_message(message_or_callback, text, keyboard, edit)

    @staticmethod
    async def _send_or_edit_message(
        message_or_callback: Message | CallbackQuery,
        text: str,
        keyboard: Any,
        edit: bool,  # noqa: FBT001
    ) -> None:
        """Отправить или редактировать сообщение."""
        if edit and hasattr(message_or_callback, "message"):
            await message_or_callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        else:
            await message_or_callback.answer(text, reply_markup=keyboard, parse_mode="HTML")
