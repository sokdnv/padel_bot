"""Скрипт для загрузки переменных окружения."""

import os
import sys
from dataclasses import dataclass

from dotenv import load_dotenv
from loguru import logger

# Загружаем переменные из .env файла
load_dotenv()


@dataclass
class Config:
    """Конфигурация бота."""

    bot_token: str
    database_url: str

    @classmethod
    def from_env(cls) -> "Config":
        """Загрузка секретиков."""
        bot_token = os.getenv("BOT_TOKEN")
        if not bot_token:
            msg = "BOT_TOKEN не найден в переменных окружения"
            raise ValueError(msg)

        database_url = os.getenv("DATABASE_URL")

        return cls(bot_token=bot_token, database_url=database_url)


def setup_logger(log_file: str = "logs/app.log", level: str = "INFO") -> logger:
    """Создаем логгер."""
    logger.remove()

    # Вывод в консоль
    logger.add(
        sys.stdout,
        level=level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level}</level> | <cyan>{message}</cyan>",
    )

    # Запись в файл
    logger.add(
        log_file,
        level=level,
        rotation="10 MB",
        retention="7 days",
        compression="zip",
        format="{time} | {level} | {message}",
    )

    return logger


logger = setup_logger()
