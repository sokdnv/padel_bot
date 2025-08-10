"""Основной скрипт для запуска бота."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.dispatcher.middlewares.base import BaseMiddleware
from aiogram.enums import ParseMode
from aiogram.types import CallbackQuery, Message, TelegramObject

from src.config import Config, logger
from src.database.db import Database
from src.handlers import init_handlers

# Импорты роутеров
from src.handlers import router as handlers_router
from src.services.core import BotConfig
from src.shared.decorators import log_handler_calls
from src.services.game_creation import GameCreationConfig, init_game_management
from src.services.game_creation import router as game_creation_router
from src.services.payments import router as payments_router

# Импорты для инициализации сервисов
from src.services.scheduler import ReminderConfig, create_reminder_system


class DatabaseMiddleware(BaseMiddleware):
    """Middleware для передачи объекта базы данных и бота в handlers."""

    def __init__(self, db: Database, bot: Bot) -> None:  # noqa: D107
        self.db = db
        self.bot = bot
        super().__init__()

    @log_handler_calls
    async def __call__(  # noqa: D102
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:  # noqa: ANN401
        # Логирование входящих событий
        if isinstance(event, Message):
            user_id = event.from_user.id
            username = event.from_user.username or "без username"
            text = event.text or "[не текст]"
            logger.info(f"📩 Сообщение от {user_id} (@{username}): {text[:50]}...")
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id
            username = event.from_user.username or "без username"
            callback_data = event.data or "[нет данных]"
            logger.info(f"🔘 Callback от {user_id} (@{username}): {callback_data}")

        data["db"] = self.db
        data["bot"] = self.bot

        try:
            result = await handler(event, data)
            # Логирование успешной обработки
            if isinstance(event, Message):
                logger.info(f"✅ Сообщение от {user_id} обработано успешно")
            elif isinstance(event, CallbackQuery):
                logger.info(f"✅ Callback от {user_id} обработан успешно")
            return result  # noqa: TRY300
        except Exception as e:
            # Логирование ошибок
            if isinstance(event, Message):
                logger.error(f"❌ Ошибка обработки сообщения от {user_id}: {e}")
            elif isinstance(event, CallbackQuery):
                logger.error(f"❌ Ошибка обработки callback от {user_id}: {e}")
            raise


def setup_logging() -> None:
    """Настройка логирования для бота и aiogram."""
    # Настройка логгера aiogram
    aiogram_logger = logging.getLogger("aiogram")
    aiogram_logger.setLevel(logging.INFO)

    # Логгер для событий диспетчера
    dispatcher_logger = logging.getLogger("aiogram.dispatcher")
    dispatcher_logger.setLevel(logging.INFO)

    # Логгер для webhook (если используется)
    webhook_logger = logging.getLogger("aiogram.webhook")
    webhook_logger.setLevel(logging.INFO)

    logger.info("Логирование настроено")


async def setup_services(bot: Bot, db: Database) -> None:
    """Настройка сервисов и обработчиков."""
    logger.info("Инициализация сервисов...")

    # Конфигурация для системы напоминаний
    reminder_config = ReminderConfig(
        reminder_hours_before=3,
        max_upcoming_games=100,
    )

    # Создание системы напоминаний
    reminder_system = create_reminder_system(bot, db, reminder_config)
    logger.info("Система напоминаний инициализирована")

    # Конфигурация для основных обработчиков
    bot_config = BotConfig(
        games_per_page=4,
        notification_enabled=True,
    )

    # Конфигурация для создания игр
    game_creation_config = GameCreationConfig(
        min_duration=60,
        max_duration=180,
        games_per_page=4,
        auto_register_creator=True,
    )

    # Инициализация обработчиков
    init_handlers(db, bot, reminder_system, bot_config)
    logger.info("Основные обработчики инициализированы")

    # Инициализация управления играми
    init_game_management(db, bot, reminder_system, game_creation_config)
    logger.info("Управление играми инициализировано")


async def setup_dispatcher(dp: Dispatcher, db: Database, bot: Bot) -> None:
    """Настройка диспетчера."""
    # Добавление middleware для базы данных и бота
    middleware = DatabaseMiddleware(db, bot)
    dp.message.middleware(middleware)
    dp.callback_query.middleware(middleware)

    # Регистрация роутеров
    dp.include_router(handlers_router)
    dp.include_router(payments_router)
    dp.include_router(game_creation_router)

    logger.info("Диспетчер настроен")


async def main() -> None:
    """Главная функция."""
    # Настройка логирования
    setup_logging()

    # Загрузка конфигурации
    try:
        config = Config.from_env()
        logger.info("Конфигурация загружена")
    except ValueError:
        logger.exception("Ошибка конфигурации")
        return

    # Инициализация бота
    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    # Получение информации о боте
    try:
        bot_info = await bot.get_me()
        logger.info(f"Бот инициализирован: @{bot_info.username} ({bot_info.first_name})")
    except Exception as e:  # noqa: BLE001
        logger.error(f"Ошибка получения информации о боте: {e}")
        logger.info("Бот инициализирован (информация недоступна)")

    # Инициализация диспетчера
    dp = Dispatcher()

    # Инициализация базы данных
    db = Database(config.database_url)

    try:
        # Подключение к базе данных
        await db.connect()
        logger.info("База данных подключена")

        # Настройка сервисов
        await setup_services(bot, db)

        # Настройка диспетчера
        await setup_dispatcher(dp, db, bot)

        # Запуск бота
        logger.info("🚀 Запуск бота...")
        logger.info("📡 Начинается polling...")
        await dp.start_polling(bot)

    except KeyboardInterrupt:
        logger.info("⏹️ Бот остановлен пользователем")
    except Exception:  # noqa: BLE001
        logger.exception("💥 Критическая ошибка запуска бота")
    finally:
        # Корректное завершение работы
        logger.info("🔄 Завершение работы...")

        # Отключение от базы данных
        await db.disconnect()
        logger.info("🗄️ База данных отключена")

        # Закрытие сессии бота
        await bot.session.close()
        logger.info("🤖 Сессия бота закрыта")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("⏹️ Бот остановлен пользователем (Ctrl+C)")
    except Exception:  # noqa: BLE001
        logger.exception("💥 Критическая ошибка")
    finally:
        logger.info("👋 Программа завершена")
