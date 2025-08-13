"""Скрипт для отправки напоминаний игрокам."""

import asyncio
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

from src.config import logger
from src.services.payments import send_payment_offer
from src.shared.formatters import Formatters
from src.shared.keyboards import CommonKeyboards


@dataclass
class ReminderConfig:
    """Конфигурация системы напоминаний."""

    timezone: timezone = timezone(timedelta(hours=3))
    reminder_hours_before: int = 3
    max_upcoming_games: int = 100


class ReminderTask:
    """Управление задачами напоминания и предложения оплаты."""

    def __init__(self, game_date: date, game_time: str | time) -> None:  # noqa: D107
        self.game_date = game_date
        self.game_time = game_time
        self.reminder_task: asyncio.Task | None = None
        self.payment_task: asyncio.Task | None = None
        self.key = self._generate_key()

    def _generate_key(self) -> str:
        """Генерация уникального ключа для задачи."""
        time_str = Formatters.format_time(self.game_time)
        return f"{self.game_date}_{time_str}"

    def cancel(self) -> None:
        """Отмена всех задач."""
        for task in [self.reminder_task, self.payment_task]:
            if task and not task.done():
                task.cancel()

    def is_active(self) -> bool:
        """Проверка активности любой задачи."""
        return any(task is not None and not task.done() for task in [self.reminder_task, self.payment_task])


class ReminderSystem:
    """Система напоминаний об играх."""

    def __init__(self, bot, database, config: ReminderConfig | None = None) -> None:  # noqa: D107, ANN001
        self.bot = bot
        self.database = database
        self.config = config or ReminderConfig()
        self.tasks: dict[str, ReminderTask] = {}

    async def schedule_reminder(self, game_date: date, game_time: str | time) -> bool:
        """Запланировать напоминание для игры."""
        try:
            parsed_time = Formatters.parse_time(game_time)
            if not parsed_time:
                logger.warning(f"Не удалось разобрать время игры: {game_time}")
                return False

            game_datetime = datetime.combine(game_date, parsed_time, tzinfo=self.config.timezone)
            reminder_time = game_datetime - timedelta(hours=self.config.reminder_hours_before)
            now = datetime.now(self.config.timezone)

            if reminder_time <= now:
                logger.debug(f"Время напоминания уже прошло для игры {game_date} {game_time}")
                return False

            task = ReminderTask(game_date, game_time)
            old_task = self.tasks.get(task.key)
            if old_task:
                old_task.cancel()

            delay = (reminder_time - now).total_seconds()
            task.reminder_task = asyncio.create_task(
                self._send_reminder_after_delay(delay, game_date),
            )

            self.tasks[task.key] = task

            return True  # noqa: TRY300

        except Exception:  # noqa: BLE001
            logger.exception("Ошибка планирования напоминания")
            return False

    async def schedule_payment_offer(self, game_date: date, game_time: str | time, duration: int = 120) -> bool:
        """Запланировать предложение оплаты после игры."""
        try:
            parsed_time = Formatters.parse_time(game_time)
            if not parsed_time:
                logger.warning(f"Не удалось разобрать время игры для оплаты: {game_time}")
                return False

            game_datetime = datetime.combine(game_date, parsed_time, tzinfo=self.config.timezone)
            payment_time = game_datetime + timedelta(minutes=duration)
            now = datetime.now(self.config.timezone)

            if payment_time <= now:
                logger.debug(f"Время предложения оплаты уже прошло для игры {game_date} {game_time}")
                return False

            task_key = f"{game_date}_{Formatters.format_time(game_time)}"
            task = self.tasks.get(task_key)
            if not task:
                task = ReminderTask(game_date, game_time)
                self.tasks[task_key] = task

            if task.payment_task:
                task.payment_task.cancel()

            delay = (payment_time - now).total_seconds()
            task.payment_task = asyncio.create_task(
                self._send_payment_offer_after_delay(delay, game_date, game_time),
            )

            return True  # noqa: TRY300

        except Exception:  # noqa: BLE001
            logger.exception("Ошибка планирования предложения оплаты")
            return False

    async def _send_reminder_after_delay(self, delay: float, game_date: date) -> None:
        """Отправить напоминание после задержки."""
        try:
            await asyncio.sleep(delay)
            await self._send_game_reminder(game_date)
        except asyncio.CancelledError:
            logger.debug(f"Напоминание для {game_date} отменено")
        except Exception:  # noqa: BLE001
            logger.exception("Ошибка отправки напоминания")

    async def _send_payment_offer_after_delay(self, delay: float, game_date: date, game_time: str | time) -> None:
        """Отправить предложение оплаты после задержки."""
        try:
            await asyncio.sleep(delay)
            await self._send_payment_offer(game_date, game_time)
        except asyncio.CancelledError:
            logger.debug(f"Предложение оплаты для {game_date} отменено")
        except Exception:  # noqa: BLE001
            logger.exception("Ошибка отправки предложения оплаты")

    async def _send_game_reminder(self, game_date: date) -> None:
        """Отправить напоминания участникам."""
        try:
            game_datetime = datetime.combine(game_date, datetime.min.time())
            game = await self.database.get_game_by_date(game_datetime)

            if not game or not game.get_players():
                logger.debug(f"Игра {game_date} не найдена или без участников")
                return

            players = game.get_players()
            users_info = await self.database.get_users_info(players)
            player_names = [users_info.get(player_id, f"User{player_id}") for player_id in players]

            message = Formatters.format_reminder_message(
                game_time=game.time,
                location=game.location,
                court=game.court,
                player_names=player_names,
                hours_before=self.config.reminder_hours_before,
            )

            success_count = 0
            for player_id in players:
                try:
                    await self.bot.send_message(
                        player_id, message, parse_mode="HTML", reply_markup=CommonKeyboards.create_delete_keyboard()
                    )
                    success_count += 1
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"Не удалось отправить напоминание игроку {player_id}: {e}")

            logger.info(
                f"Отправлены напоминания для игры {Formatters.format_date(game_date)} "
                f"{Formatters.format_time(game.time)} ({success_count}/{len(players)} успешно)",
            )

        except Exception:  # noqa: BLE001
            logger.exception("Ошибка отправки напоминаний")

    async def _send_payment_offer(self, game_date: date, game_time: str | time) -> None:
        """Отправить предложение оплаты админу игры."""
        try:
            game_datetime = datetime.combine(game_date, datetime.min.time())
            game = await self.database.get_game_by_date(game_datetime)

            if not game or not game.admin:
                logger.debug(f"Игра {game_date} не найдена или без админа")
                return

            await send_payment_offer(
                bot=self.bot,
                admin_id=game.admin,
                game_date=Formatters.format_date(game_date),
                game_time=Formatters.format_time(game_time),
            )

            logger.info(
                f"Отправлено предложение оплаты админу {game.admin} "
                f"для игры {Formatters.format_date(game_date)} {Formatters.format_time(game_time)}",
            )

        except Exception:  # noqa: BLE001
            logger.exception("Ошибка отправки предложения оплаты")

    async def schedule_all_upcoming_games(self) -> None:
        """Запланировать напоминания и предложения оплаты для всех предстоящих игр."""
        try:
            games = await self.database.get_upcoming_games_with_time(
                limit=self.config.max_upcoming_games,
            )

            reminder_count = 0
            payment_count = 0

            for game in games:
                if game.time:
                    if game.get_players():  # noqa: SIM102
                        if await self.schedule_reminder(game.date.date(), game.time):
                            reminder_count += 1

                    if game.admin:  # noqa: SIM102
                        if await self.schedule_payment_offer(game.date.date(), game.time, game.duration):
                            payment_count += 1

            logger.info(
                f"Запланировано {reminder_count} напоминаний и {payment_count} предложений оплаты из {len(games)} игр",
            )

        except Exception:  # noqa: BLE001
            logger.exception("Ошибка при планировании напоминаний")


def create_reminder_system(bot, database, config: ReminderConfig | None = None) -> ReminderSystem:  # noqa: ANN001
    """Создать и инициализировать систему напоминаний."""
    system = ReminderSystem(bot, database, config)
    asyncio.create_task(system.schedule_all_upcoming_games())  # noqa: RUF006
    return system


_global_reminder_system: ReminderSystem | None = None


async def schedule_reminder(game_date, game_time):  # noqa: ANN201, ANN001
    """Глобальная функция для планирования напоминания (для обратной совместимости)."""
    if _global_reminder_system is None:
        msg = "Система напоминаний не инициализирована. Вызовите init_reminder_system() сначала."
        raise RuntimeError(msg)

    return await _global_reminder_system.schedule_reminder(game_date, game_time)
