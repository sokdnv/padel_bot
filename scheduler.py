import asyncio
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

# Часовой пояс GMT+3
MOSCOW_TZ = timezone(timedelta(hours=3))

# Глобальные переменные
bot_instance = None
db_instance = None
reminder_tasks = {}


async def schedule_reminder(game_date, game_time):
    """Запланировать напоминание для игры"""
    if not game_time:
        return  # Нет времени - нет напоминания

    try:
        # game_date это date объект из БД
        # game_time это time объект из БД

        # Создаем datetime в часовом поясе GMT+3
        if isinstance(game_time, str):
            time_obj = datetime.strptime(game_time, "%H:%M:%S").time()
        else:
            time_obj = game_time

        # Комбинируем дату и время и устанавливаем часовой пояс GMT+3
        game_datetime = datetime.combine(game_date, time_obj, tzinfo=MOSCOW_TZ)

        # Время напоминания - за 3 часа
        reminder_time = game_datetime - timedelta(hours=3)

        # Текущее время в GMT+3
        now = datetime.now(MOSCOW_TZ)

        # Проверяем, что время в будущем
        if reminder_time <= now:
            return

        # Ключ для идентификации
        task_key = f"{game_date}_{game_time}"

        # Отменяем старую задачу если есть
        if task_key in reminder_tasks:
            reminder_tasks[task_key].cancel()

        # Создаем новую задачу
        delay = (reminder_time - now).total_seconds()
        task = asyncio.create_task(send_reminder_after_delay(delay, game_date))
        reminder_tasks[task_key] = task

        logger.info(f"Запланировано напоминание для {game_date} {game_time} (через {delay / 3600:.1f} часов)")

    except Exception as e:
        logger.error(f"Ошибка планирования напоминания: {e}")


async def send_reminder_after_delay(delay, game_date):
    """Отправить напоминание после задержки"""
    try:
        await asyncio.sleep(delay)
        await send_game_reminder(game_date)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"Ошибка отправки напоминания: {e}")


async def send_game_reminder(game_date):
    """Отправить напоминания участникам"""
    try:
        # Получаем актуальную игру
        game = await db_instance.get_game_by_date(datetime.combine(game_date, datetime.min.time()))
        if not game:
            return

        players = game.get_players()
        if not players:
            return

        # Получаем информацию об игроках
        users_info = await db_instance.get_users_info(players)

        # Формируем список участников
        player_names = []
        for player_id in players:
            if player_id in users_info:
                player_names.append(users_info[player_id])
            else:
                player_names.append(f"User{player_id}")

        # Формируем сообщение
        date_str = game_date.strftime("%d.%m.%Y")

        # Форматируем время из БД
        if game.time:
            if isinstance(game.time, str):
                time_str = game.time[:5]  # Обрезаем секунды 15:00:00 -> 15:00
            else:
                time_str = game.time.strftime("%H:%M")
        else:
            time_str = "время не указано"

        location_str = game.location if game.location else "место не указано"

        message = (
            f"⏰ <b>Напоминание об игре!</b>\n\n"
            f"🎾 Игра через 3 часа\n"
            f"🕐 {time_str}\n"
            f"📍 {location_str}\n\n"
            f"👥 {', '.join(player_names)}\n\n"
            f"До встречи на корте! 🎾"
        )

        # Отправляем всем участникам
        for player_id in players:
            try:
                await bot_instance.send_message(player_id, message, parse_mode="HTML")
            except Exception as e:
                logger.warning(f"Не удалось отправить напоминание игроку {player_id}: {e}")

        logger.info(f"Отправлены напоминания для игры {date_str} {time_str}")

    except Exception as e:
        logger.error(f"Ошибка отправки напоминаний: {e}")


async def check_and_schedule_all_games():
    """Проверить все игры и запланировать напоминания"""
    try:
        # Получаем игры на ближайшие дни с указанным временем
        games = await db_instance.get_upcoming_games_with_time(limit=100)

        for game in games:
            if game.time and len(game.get_players()) > 0:
                await schedule_reminder(game.date.date(), game.time)

    except Exception as e:
        logger.error(f"Ошибка при проверке игр: {e}")


def init_reminder_system(bot, db):
    """Инициализировать систему напоминаний"""
    global bot_instance, db_instance
    bot_instance = bot
    db_instance = db

    # Запланировать проверку существующих игр
    asyncio.create_task(check_and_schedule_all_games())

    logger.info("Система напоминаний инициализирована")
