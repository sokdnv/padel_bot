"""Скрипт для отправки напоминаний игрокам."""

import asyncio
import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

logger = logging.getLogger(__name__)


@dataclass
class ReminderConfig:
    """Конфигурация системы напоминаний."""

    timezone: timezone = timezone(timedelta(hours=3))
    reminder_hours_before: int = 3
    max_upcoming_games: int = 100


class TimeFormatter:
    """Утилиты для форматирования времени."""

    @staticmethod
    def parse_time(time_value: str | time) -> time | None:
        """Парсинг времени из различных форматов."""
        if not time_value:
            return None

        if isinstance(time_value, str):
            try:
                return datetime.strptime(time_value, "%H:%M:%S").time()  # noqa: DTZ007
            except ValueError:
                try:
                    return datetime.strptime(time_value, "%H:%M").time()  # noqa: DTZ007
                except ValueError:
                    return None

        return time_value if isinstance(time_value, time) else None

    @staticmethod
    def format_time(time_value: str | time) -> str:
        """Форматирование времени для отображения."""
        if not time_value:
            return "время не указано"

        if isinstance(time_value, str):
            return time_value[:5] if len(time_value) >= 5 else time_value  # noqa: PLR2004

        return time_value.strftime("%H:%M")

    @staticmethod
    def format_date(date_value: date) -> str:
        """Форматирование даты для отображения."""
        return date_value.strftime("%d.%m.%Y")


class MessageFormatter:
    """Форматирование сообщений."""

    @staticmethod
    def format_reminder_message(
            game_time: str | time,
            location: str | None,
            court: int | None,
            player_names: list[str],
            hours_before: int = 3,
    ) -> str:
        """Форматирование сообщения-напоминания."""
        time_str = TimeFormatter.format_time(game_time)
        location_str = location if location else "место не указано"
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


class ReminderTask:
    """Управление отдельной задачей напоминания."""

    def __init__(self, game_date: date, game_time: str | time) -> None:  # noqa: D107
        self.game_date = game_date
        self.game_time = game_time
        self.task: asyncio.Task | None = None
        self.key = self._generate_key()

    def _generate_key(self) -> str:
        """Генерация уникального ключа для задачи."""
        time_str = TimeFormatter.format_time(self.game_time)
        return f"{self.game_date}_{time_str}"

    def cancel(self) -> None:
        """Отмена задачи."""
        if self.task and not self.task.done():
            self.task.cancel()

    def is_active(self) -> bool:
        """Проверка активности задачи."""
        return self.task is not None and not self.task.done()


class ReminderSystem:
    """Система напоминаний об играх."""

    def __init__(self, bot, database, config: ReminderConfig | None = None) -> None:  # noqa: D107, ANN001
        self.bot = bot
        self.database = database
        self.config = config or ReminderConfig()
        self.reminder_tasks: dict[str, ReminderTask] = {}

    async def schedule_reminder(self, game_date: date, game_time: str | time) -> bool:
        """Запланировать напоминание для игры."""
        try:
            parsed_time = TimeFormatter.parse_time(game_time)
            if not parsed_time:
                logger.warning(f"Не удалось разобрать время игры: {game_time}")
                return False

            # Создаем datetime в нужном часовом поясе
            game_datetime = datetime.combine(game_date, parsed_time, tzinfo=self.config.timezone)
            reminder_time = game_datetime - timedelta(hours=self.config.reminder_hours_before)

            # Проверяем, что время в будущем
            now = datetime.now(self.config.timezone)
            if reminder_time <= now:
                logger.debug(f"Время напоминания уже прошло для игры {game_date} {game_time}")
                return False

            # Создаем задачу напоминания
            reminder_task = ReminderTask(game_date, game_time)

            # Отменяем старую задачу если есть
            old_task = self.reminder_tasks.get(reminder_task.key)
            if old_task:
                old_task.cancel()

            # Создаем новую задачу
            delay = (reminder_time - now).total_seconds()
            reminder_task.task = asyncio.create_task(
                self._send_reminder_after_delay(delay, game_date),
            )

            self.reminder_tasks[reminder_task.key] = reminder_task

            logger.info(
                f"Запланировано напоминание для {game_date} {TimeFormatter.format_time(game_time)} "
                f"(через {delay / 3600:.1f} часов)",
            )
            return True  # noqa: TRY300

        except Exception:
            logger.exception("Ошибка планирования напоминания")
            return False

    async def _send_reminder_after_delay(self, delay: float, game_date: date) -> None:
        """Отправить напоминание после задержки."""
        try:
            await asyncio.sleep(delay)
            await self._send_game_reminder(game_date)
        except asyncio.CancelledError:
            logger.debug(f"Напоминание для {game_date} отменено")
        except Exception:
            logger.exception("Ошибка отправки напоминания")

    async def _send_game_reminder(self, game_date: date) -> None:
        """Отправить напоминания участникам."""
        try:
            # Получаем актуальную игру
            game_datetime = datetime.combine(game_date, datetime.min.time())
            game = await self.database.get_game_by_date(game_datetime)

            if not game or not game.get_players():
                logger.debug(f"Игра {game_date} не найдена или без участников")
                return

            # Получаем информацию об игроках
            players = game.get_players()
            users_info = await self.database.get_users_info(players)

            # Формируем список имен участников
            player_names = [
                users_info.get(player_id, f"User{player_id}")
                for player_id in players
            ]

            # Формируем сообщение
            message = MessageFormatter.format_reminder_message(
                game_time=game.time,
                location=game.location,
                court=game.court,
                player_names=player_names,
                hours_before=self.config.reminder_hours_before,
            )

            # Отправляем всем участникам
            success_count = 0
            for player_id in players:
                try:
                    await self.bot.send_message(player_id, message, parse_mode="HTML")
                    success_count += 1
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"Не удалось отправить напоминание игроку {player_id}: {e}")

            logger.info(
                f"Отправлены напоминания для игры {TimeFormatter.format_date(game_date)} "
                f"{TimeFormatter.format_time(game.time)} ({success_count}/{len(players)} успешно)",
            )

        except Exception:
            logger.exception("Ошибка отправки напоминаний")

    async def schedule_all_upcoming_games(self) -> None:
        """Запланировать напоминания для всех предстоящих игр."""
        try:
            games = await self.database.get_upcoming_games_with_time(
                limit=self.config.max_upcoming_games,
            )

            scheduled_count = 0
            for game in games:
                if game.time and game.get_players():
                    success = await self.schedule_reminder(game.date.date(), game.time)
                    if success:
                        scheduled_count += 1

            logger.info(f"Запланировано {scheduled_count} напоминаний из {len(games)} игр")

        except Exception:
            logger.exception("Ошибка при планировании напоминаний")


# Фабричная функция для создания системы напоминаний
def create_reminder_system(bot, database, config: ReminderConfig | None = None) -> ReminderSystem:  # noqa: ANN001
    """Создать и инициализировать систему напоминаний."""
    system = ReminderSystem(bot, database, config)

    # Запланировать проверку существующих игр
    asyncio.create_task(system.schedule_all_upcoming_games())  # noqa: RUF006

    logger.info("Система напоминаний инициализирована")
    return system


_global_reminder_system: ReminderSystem | None = None


async def schedule_reminder(game_date, game_time):  # noqa: ANN201, ANN001
    """Глобальная функция для планирования напоминания (для обратной совместимости)."""
    if _global_reminder_system is None:
        msg = "Система напоминаний не инициализирована. Вызовите init_reminder_system() сначала."
        raise RuntimeError(msg)

    return await _global_reminder_system.schedule_reminder(game_date, game_time)
