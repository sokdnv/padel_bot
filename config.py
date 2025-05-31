import os
from dataclasses import dataclass
from dotenv import load_dotenv

# Загружаем переменные из .env файла
load_dotenv()


@dataclass
class Config:
    """Конфигурация бота"""

    bot_token: str
    database_url: str

    @classmethod
    def from_env(cls) -> "Config":
        bot_token = os.getenv("BOT_TOKEN")
        if not bot_token:
            raise ValueError("BOT_TOKEN не найден в переменных окружения")

        database_url = os.getenv("DATABASE_URL", "postgresql://user:password@localhost/padel_bot")

        return cls(bot_token=bot_token, database_url=database_url)
