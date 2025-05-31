import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import TelegramObject
from aiogram.dispatcher.middlewares.base import BaseMiddleware
from typing import Callable, Dict, Any, Awaitable

from config import Config
from database import Database
from handlers import router

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class DatabaseMiddleware(BaseMiddleware):
    """Middleware для передачи объекта базы данных в handlers"""

    def __init__(self, db: Database):
        self.db = db
        super().__init__()

    async def __call__(
            self,
            handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
            event: TelegramObject,
            data: Dict[str, Any]
    ) -> Any:
        data["db"] = self.db
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
    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )

    # Инициализация диспетчера
    dp = Dispatcher()

    # Инициализация базы данных
    db = Database(config.database_url)

    try:
        await db.connect()

        # Добавление middleware для базы данных
        dp.message.middleware(DatabaseMiddleware(db))
        dp.callback_query.middleware(DatabaseMiddleware(db))

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
