import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.dispatcher.middlewares.base import BaseMiddleware
from aiogram.enums import ParseMode
from aiogram.types import TelegramObject

from config import Config
from database import Database
from handlers import router
from scheduler import init_reminder_system

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class DatabaseMiddleware(BaseMiddleware):
    """Middleware для передачи объекта базы данных и бота в handlers"""

    def __init__(self, db: Database, bot: Bot):
        self.db = db
        self.bot = bot
        super().__init__()

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        data["db"] = self.db
        data["bot"] = self.bot
        return await handler(event, data)


async def main():
    """Главная функция"""
    # Загрузка конфигурации
    try:
        config = Config.from_env()
    except ValueError as e:
        logger.error(f"Ошибка конфигурации: {e}")
        return

    # Инициализация бота
    bot = Bot(token=config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

    # Инициализация диспетчера
    dp = Dispatcher()

    # Инициализация базы данных
    db = Database(config.database_url)

    try:
        await db.connect()

        init_reminder_system(bot, db)

        # Добавление middleware для базы данных и бота
        middleware = DatabaseMiddleware(db, bot)
        dp.message.middleware(middleware)
        dp.callback_query.middleware(middleware)

        # Регистрация роутеров
        dp.include_router(router)

        # Запуск бота
        logger.info("Бот запускается...")
        await dp.start_polling(bot)

    except Exception as e:
        logger.error(f"Ошибка запуска бота: {e}")
    finally:
        await db.disconnect()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
