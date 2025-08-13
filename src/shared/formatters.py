"""Объединенные форматеры для всего приложения."""

from datetime import date, datetime, time
from typing import Any

from aiogram.types import User


class Formatters:
    """Объединенный класс форматеров."""

    @staticmethod
    def format_date(date_value: datetime | date) -> str:
        """Форматировать дату."""
        if isinstance(date_value, datetime):
            return date_value.strftime("%d.%m.%Y")
        return date_value.strftime("%d.%m.%Y")

    @staticmethod
    def format_short_date(date_value: datetime | date) -> str:
        """Форматировать короткую дату."""
        if isinstance(date_value, datetime):
            return date_value.strftime("%d.%m")
        return date_value.strftime("%d.%m")

    @staticmethod
    def format_time(time_value: str | time | None) -> str:
        """Форматирование времени для отображения."""
        if not time_value:
            return "время не указано"

        if isinstance(time_value, str):
            return time_value[:5] if len(time_value) >= 5 else time_value

        return time_value.strftime("%H:%M")

    @staticmethod
    def format_time_duration(time_str: str, duration: int) -> str:
        """Форматировать время и длительность."""
        time_info = time_str
        if duration:
            hours = duration // 60
            minutes = duration % 60
            if minutes == 0:
                time_info += f" ({hours}ч)"
            else:
                time_info += f" ({hours}ч {minutes}м)"
        return time_info

    @staticmethod
    def format_duration(duration: int) -> str:
        """Форматировать длительность."""
        hours = duration // 60
        minutes = duration % 60
        if minutes == 0:
            return f"{hours}ч"
        return f"{hours}ч {minutes}м"

    @staticmethod
    def get_display_name(user: User) -> str:
        """Получить отображаемое имя пользователя."""
        if user.username:
            return f"@{user.username}"
        if user.first_name:
            return user.first_name
        return f"User{user.id}"

    @staticmethod
    def parse_time(time_value: str | time) -> time | None:
        """Парсинг времени из различных форматов."""
        if not time_value:
            return None

        if isinstance(time_value, str):
            try:
                return datetime.strptime(time_value, "%H:%M:%S").time()
            except ValueError:
                try:
                    return datetime.strptime(time_value, "%H:%M").time()
                except ValueError:
                    return None

        return time_value if isinstance(time_value, time) else None

    @staticmethod
    async def format_games_list(games: list, users_info: dict[int, str] | None = None) -> str:
        """Форматировать список игр для отображения."""
        if not games:
            return "🚫 Нет доступных игр"

        text = ""
        for game in games:
            date_str = Formatters.format_date(game.date)
            players_count = len(game.get_players())
            free_slots = game.free_slots()
            status_emoji = "🔍" if free_slots > 0 else "✅"

            text += f"{status_emoji} <b>{date_str}</b>  "

            if game.time:
                time_info = Formatters.format_time_duration(game.time, game.duration)
                text += f"{time_info}\n"

            if game.location:
                text += f"📍 {game.location}\n"
            text += f"🎾 Корт №{game.court or 'не указан'}\n"

            if players_count > 0:
                if users_info:
                    player_names = [users_info.get(player_id, f"User{player_id}") for player_id in game.get_players()]
                    text += f"👥 Записаны: {', '.join(player_names)}\n"
                else:
                    text += f"👥 Записаны: {players_count} игрок(ов)\n"

            text += "\n"

        return text

    @staticmethod
    def format_reminder_message(
        game_time: str | time,
        location: str | None,
        court: int | None,
        player_names: list[str],
        hours_before: int = 3,
    ) -> str:
        """Форматирование сообщения-напоминания."""
        time_str = Formatters.format_time(game_time)
        location_str = location or "место не указано"
        court_str = f"Корт №{court}" if court else "номер корта не указан"

        return (
            f"⏰ <b>Напоминание об игре!</b>\n\n"
            f"🎾 Игра через {hours_before} часа\n"
            f"🕐 {time_str}\n"
            f"📍 {location_str}\n"
            f"🏟️ {court_str}\n\n"
            f"👥 {', '.join(player_names)}\n\n"
            f"До встречи на корте! 🎾"
        )

    @staticmethod
    def format_game_success_message(game_data: dict[str, Any]) -> str:
        """Сообщение об успешном создании игры."""
        date_str = Formatters.format_date(game_data["date"])
        time_str = game_data["time"].strftime("%H:%M")
        duration_str = Formatters.format_duration(game_data["duration"])

        return (
            f"✅ <b>Игра создана!</b>\n\n"
            f"📅 Дата: {date_str}\n"
            f"🕐 Время: {time_str}\n"
            f"⏱ Продолжительность: {duration_str}\n"
            f"📍 Локация: {game_data['location']}\n"
            f"🎾 Корт: №{game_data['court']}\n\n"
        )

    @staticmethod
    def format_game_notification_message(game_data: dict[str, Any], creator: User) -> str:
        """Уведомление о новой игре."""
        date_str = Formatters.format_date(game_data["date"])
        time_str = game_data["time"].strftime("%H:%M")
        creator_name = Formatters.get_display_name(creator)
        duration_str = Formatters.format_duration(game_data["duration"])

        return (
            f"🆕 <b>Новая игра создана!</b>\n\n"
            f"👤 Создатель: {creator_name}\n"
            f"📅 Дата: {date_str}\n"
            f"🕐 Время: {time_str}\n"
            f"⏱ Продолжительность: {duration_str}\n"
            f"📍 Локация: {game_data['location']}\n"
            f"🎾 Корт: №{game_data['court']}\n\n"
        )
