import logging
from dataclasses import dataclass
from datetime import datetime

import asyncpg

logger = logging.getLogger(__name__)


@dataclass
class GameSlot:
    """Модель игрового слота"""

    date: datetime
    time: datetime.time = None
    duration: int = 120
    location: str | None = None
    creator_id: int | None = None
    player_1: int | None = None
    player_2: int | None = None
    player_3: int | None = None
    player_4: int | None = None

    def get_players(self) -> list[int]:
        """Получить список зарегистрированных игроков"""
        return [p for p in [self.player_1, self.player_2, self.player_3, self.player_4] if p is not None]

    def free_slots(self) -> int:
        """Количество свободных мест"""
        return 4 - len(self.get_players())

    def is_full(self) -> bool:
        """Проверить, заполнена ли игра"""
        return self.free_slots() == 0

    def has_player(self, user_id: int) -> bool:
        """Проверить, зарегистрирован ли игрок"""
        return user_id in self.get_players()


class Database:
    """Класс для работы с базой данных"""

    def __init__(self, database_url: str):
        self.database_url = database_url
        self.pool: asyncpg.Pool | None = None

    async def connect(self):
        """Подключение к базе данных"""
        try:
            self.pool = await asyncpg.create_pool(self.database_url)
            logger.info("Подключение к базе данных установлено")
        except Exception as e:
            logger.error(f"Ошибка подключения к базе данных: {e}")
            raise

    async def disconnect(self):
        """Отключение от базы данных"""
        if self.pool:
            await self.pool.close()
            logger.info("Соединение с базой данных закрыто")

        async with self.pool.acquire() as conn:
            for thursday in thursdays:
                await conn.execute(
                    """
                                   INSERT INTO games (date)
                                   VALUES ($1)
                                   ON CONFLICT (date) DO NOTHING
                                   """,
                    thursday,
                )

        logger.info(f"Инициализированы игры на {len(thursdays)} дат (включая 29.08.2025)")

    async def get_all_users(self) -> list[int]:
        """Получить список всех зарегистрированных пользователей"""
        query = "SELECT user_id FROM users ORDER BY registered_at"
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query)
        return [row["user_id"] for row in rows]

    async def get_upcoming_games(self, limit: int = 20, offset: int = 0) -> list[GameSlot]:
        """Получить предстоящие игры с пагинацией"""
        query = """
                SELECT date, player_1, player_2, player_3, player_4, time, duration, location
                FROM games
                WHERE date >= CURRENT_DATE
                ORDER BY date
                LIMIT $1 OFFSET $2 \
                """

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, limit, offset)

        return [
            GameSlot(
                date=datetime.combine(row["date"], datetime.min.time()),
                player_1=row["player_1"],
                player_2=row["player_2"],
                player_3=row["player_3"],
                player_4=row["player_4"],
                time=row["time"].strftime("%H:%M") if row["time"] else None,
                duration=row["duration"],
                location=row["location"],
            )
            for row in rows
        ]

    async def get_available_games(
        self,
        limit: int = 20,
        offset: int = 0,
        exclude_user_id: int = None,
    ) -> list[GameSlot]:
        """Получить игры со свободными местами"""
        if exclude_user_id:
            query = """
                    SELECT date, player_1, player_2, player_3, player_4, time, duration, location
                    FROM games
                    WHERE date >= CURRENT_DATE
                      AND (player_1 IS NULL OR player_2 IS NULL OR player_3 IS NULL OR player_4 IS NULL)
                      AND NOT (player_1 = $3 OR player_2 = $3 OR player_3 = $3 OR player_4 = $3)
                    ORDER BY date
                    LIMIT $1 OFFSET $2
                    """
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, limit, offset, exclude_user_id)
        else:
            query = """
                    SELECT date, player_1, player_2, player_3, player_4, time, duration, location
                    FROM games
                    WHERE date >= CURRENT_DATE
                      AND (player_1 IS NULL OR player_2 IS NULL OR player_3 IS NULL OR player_4 IS NULL)
                    ORDER BY date
                    LIMIT $1 OFFSET $2
                    """
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, limit, offset)

        return [
            GameSlot(
                date=datetime.combine(row["date"], datetime.min.time()),
                player_1=row["player_1"],
                player_2=row["player_2"],
                player_3=row["player_3"],
                player_4=row["player_4"],
                time=row["time"].strftime("%H:%M") if row["time"] else None,
                duration=row["duration"],
                location=row["location"],
            )
            for row in rows
        ]

    async def get_user_games(self, user_id: int, limit: int = 20, offset: int = 0) -> list[GameSlot]:
        """Получить игры пользователя"""
        query = """
                SELECT date, player_1, player_2, player_3, player_4, time, duration, location
                FROM games
                WHERE date >= CURRENT_DATE
                  AND (player_1 = $1 OR player_2 = $1 OR player_3 = $1 OR player_4 = $1)
                ORDER BY date
                LIMIT $2 OFFSET $3 \
                """

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, user_id, limit, offset)

        return [
            GameSlot(
                date=datetime.combine(row["date"], datetime.min.time()),
                player_1=row["player_1"],
                player_2=row["player_2"],
                player_3=row["player_3"],
                player_4=row["player_4"],
                time=row["time"].strftime("%H:%M") if row["time"] else None,
                duration=row["duration"],
                location=row["location"],
            )
            for row in rows
        ]

    async def register_player(self, date: datetime, user_id: int) -> bool:
        """Записать игрока на игру"""
        async with self.pool.acquire() as conn:
            # Получить текущее состояние игры
            game = await conn.fetchrow(
                "SELECT player_1, player_2, player_3, player_4 FROM games WHERE date = $1",
                date.date(),
            )

            if not game:
                return False

            # Проверить, не записан ли игрок уже
            players = [game["player_1"], game["player_2"], game["player_3"], game["player_4"]]
            if user_id in players:
                return False

            # Найти свободное место
            for i, player in enumerate(players, 1):
                if player is None:
                    await conn.execute(f"UPDATE games SET player_{i} = $1 WHERE date = $2", user_id, date.date())
                    logger.info(f"Игрок {user_id} записан на {date.date()}")
                    return True

            return False  # Нет свободных мест

    async def unregister_player(self, date: datetime, user_id: int) -> bool:
        """Отписать игрока от игры"""
        async with self.pool.acquire() as conn:
            game = await conn.fetchrow(
                "SELECT player_1, player_2, player_3, player_4 FROM games WHERE date = $1",
                date.date(),
            )

            if not game:
                return False

            # Найти игрока и удалить
            players = [game["player_1"], game["player_2"], game["player_3"], game["player_4"]]
            for i, player in enumerate(players, 1):
                if player == user_id:
                    await conn.execute(f"UPDATE games SET player_{i} = $1 WHERE date = $2", None, date.date())
                    logger.info(f"Игрок {user_id} отписан от {date.date()}")
                    return True

            return False

    async def get_game_by_date(self, date: datetime) -> GameSlot | None:
        """Получить игру по дате"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT date, player_1, player_2, player_3, player_4, time, duration, location FROM games WHERE date = $1",
                date.date(),
            )

        if not row:
            return None

        return GameSlot(
            date=datetime.combine(row["date"], datetime.min.time()),
            player_1=row["player_1"],
            player_2=row["player_2"],
            player_3=row["player_3"],
            player_4=row["player_4"],
            time=row["time"].strftime("%H:%M") if row["time"] else None,
            duration=row["duration"],
            location=row["location"],
        )

    async def get_users_info(self, user_ids: list[int]) -> dict:
        """Получить информацию о пользователях"""
        if not user_ids:
            return {}

        placeholders = ", ".join([f"${i + 1}" for i in range(len(user_ids))])
        query = f"""
        SELECT user_id, username, first_name, last_name 
        FROM users 
        WHERE user_id IN ({placeholders})
        """

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, *user_ids)

        users_info = {}
        for row in rows:
            user_id = row["user_id"]
            if row["username"]:
                display_name = f"@{row['username']}"
            elif row["first_name"]:
                display_name = row["first_name"]
                if row["last_name"]:
                    display_name += f" {row['last_name']}"
            else:
                display_name = f"User{user_id}"

            users_info[user_id] = display_name

        return users_info

    async def count_upcoming_games(self) -> int:
        """Подсчитать общее количество предстоящих игр"""
        query = "SELECT COUNT(*) FROM games WHERE date >= CURRENT_DATE"
        async with self.pool.acquire() as conn:
            return await conn.fetchval(query)

    async def count_available_games(self) -> int:
        """Подсчитать количество игр со свободными местами"""
        query = """
                SELECT COUNT(*) FROM games
                WHERE date >= CURRENT_DATE
                  AND (player_1 IS NULL OR player_2 IS NULL OR player_3 IS NULL OR player_4 IS NULL) \
                """
        async with self.pool.acquire() as conn:
            return await conn.fetchval(query)

    async def count_user_games(self, user_id: int) -> int:
        """Подсчитать количество игр пользователя"""
        query = """
                SELECT COUNT(*) FROM games
                WHERE date >= CURRENT_DATE
                  AND (player_1 = $1 OR player_2 = $1 OR player_3 = $1 OR player_4 = $1) \
                """
        async with self.pool.acquire() as conn:
            return await conn.fetchval(query, user_id)

    async def save_user(self, user_id: int, username: str = None, first_name: str = None, last_name: str = None):
        """Сохранить информацию о пользователе"""
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                               INSERT INTO users (user_id, username, first_name, last_name)
                               VALUES ($1, $2, $3, $4)
                               ON CONFLICT (user_id) DO UPDATE SET
                                                                   username = EXCLUDED.username,
                                                                   first_name = EXCLUDED.first_name,
                                                                   last_name = EXCLUDED.last_name
                               """,
                user_id,
                username,
                first_name,
                last_name,
            )

    async def count_available_games_excluding_user(self, user_id: int) -> int:
        """Подсчитать количество игр со свободными местами, исключая игры пользователя"""
        query = """
                SELECT COUNT(*) FROM games
                WHERE date >= CURRENT_DATE
                  AND (player_1 IS NULL OR player_2 IS NULL OR player_3 IS NULL OR player_4 IS NULL)
                  AND NOT (player_1 = $1 OR player_2 = $1 OR player_3 = $1 OR player_4 = $1)
                """
        async with self.pool.acquire() as conn:
            return await conn.fetchval(query, user_id)

    async def get_upcoming_games_with_time(self, limit: int = 100, offset: int = 0) -> list[GameSlot]:
        """Получить предстоящие игры с указанным временем"""
        query = """
                SELECT date, \
                       player_1, \
                       player_2, \
                       player_3, \
                       player_4, \
                       time, \
                       duration, \
                       location
                FROM games
                WHERE date >= CURRENT_DATE
                  AND time IS NOT NULL
                ORDER BY date, time
                LIMIT $1 OFFSET $2
                """

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, limit, offset)

        return [
            GameSlot(
                date=datetime.combine(row["date"], datetime.min.time()),
                player_1=row["player_1"],
                player_2=row["player_2"],
                player_3=row["player_3"],
                player_4=row["player_4"],
                time=row["time"],
                duration=row["duration"],
                location=row["location"],
            )
            for row in rows
        ]
