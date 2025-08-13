"""Классы для взаимодействия с базой данных."""

from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime

import asyncpg

from src.config import logger
from src.database.queries import SQLQueries
from src.shared.decorators import database_operation


@dataclass
class GameSlot:
    """Модель игрового слота."""

    date: datetime
    time: datetime.time = None
    duration: int = 120
    location: str | None = None
    admin: int | None = None
    player_1: int | None = None
    player_2: int | None = None
    player_3: int | None = None
    player_4: int | None = None
    court: int | None = None

    def get_players(self) -> list[int]:
        """Получить список зарегистрированных игроков."""
        return [p for p in [self.player_1, self.player_2, self.player_3, self.player_4] if p is not None]

    def free_slots(self) -> int:
        """Количество свободных мест."""
        return 4 - len(self.get_players())

    def is_full(self) -> bool:
        """Проверить, заполнена ли игра."""
        return self.free_slots() == 0

    def has_player(self, user_id: int) -> bool:
        """Проверить, зарегистрирован ли игрок."""
        return user_id in self.get_players()


class Database:  # noqa: PLR0904
    """Класс для работы с базой данных."""

    def __init__(self, database_url: str) -> None:  # noqa: D107
        self.database_url = database_url
        self.pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        """Подключение к базе данных."""
        try:
            self.pool = await asyncpg.create_pool(self.database_url)
            logger.info("Подключение к базе данных установлено")
        except Exception:
            logger.exception("Ошибка подключения к базе данных")
            raise

    async def disconnect(self) -> None:
        """Отключение от базы данных."""
        if self.pool:
            await self.pool.close()
            self.pool = None
            logger.info("Соединение с базой данных закрыто")

    @asynccontextmanager
    async def get_connection(self):  # noqa: ANN201
        """Контекстный менеджер для получения соединения."""
        if not self.pool:
            msg = "База данных не подключена"
            raise RuntimeError(msg)

        async with self.pool.acquire() as conn:
            yield conn

    @staticmethod
    def _row_to_game_slot(row: asyncpg.Record) -> GameSlot:
        """Конвертировать строку БД в объект GameSlot."""
        return GameSlot(
            date=datetime.combine(row["date"], datetime.min.time()),
            player_1=row["player_1"],
            player_2=row["player_2"],
            player_3=row["player_3"],
            player_4=row["player_4"],
            time=row["time"].strftime("%H:%M") if row["time"] else None,
            duration=row["duration"],
            location=row["location"],
            court=row["court"],
            admin=row.get("admin"),
        )

    @staticmethod
    def _format_user_display_name(row: asyncpg.Record) -> str:
        """Форматировать отображаемое имя пользователя."""
        user_id = row["user_id"]

        if row["username"]:
            return f"@{row['username']}"
        if row["first_name"]:
            display_name = row["first_name"]
            if row["last_name"]:
                display_name += f" {row['last_name']}"
            return display_name
        return f"User{user_id}"

    async def _execute_games_query(self, query: str, *args) -> list[GameSlot]:  # noqa: ANN002
        """Выполнить запрос и вернуть список игр."""
        async with self.get_connection() as conn:
            rows = await conn.fetch(query, *args)
        return [self._row_to_game_slot(row) for row in rows]

    async def _execute_count_query(self, query: str, *args) -> int:  # noqa: ANN002
        """Выполнить запрос на подсчет."""
        async with self.get_connection() as conn:
            return await conn.fetchval(query, *args) or 0

    async def initialize_games(self, thursdays: list[datetime]) -> None:
        """Инициализация игр на указанные даты."""
        async with self.get_connection() as conn:
            for thursday in thursdays:
                await conn.execute(
                    """
                    INSERT INTO games (date)
                    VALUES ($1)
                    ON CONFLICT (date) DO NOTHING
                    """,
                    thursday,
                )
        logger.info(f"Инициализированы игры на {len(thursdays)} дат")

    async def get_all_users(self) -> list[int]:
        """Получить список всех зарегистрированных пользователей."""
        async with self.get_connection() as conn:
            rows = await conn.fetch("SELECT user_id FROM users ORDER BY registered_at")
        return [row["user_id"] for row in rows]

    async def get_upcoming_games(self, limit: int = 20, offset: int = 0) -> list[GameSlot]:
        """Получить предстоящие игры с пагинацией."""
        return await self._execute_games_query(SQLQueries.GET_UPCOMING_GAMES, limit, offset)

    async def get_available_games(
        self,
        limit: int = 20,
        offset: int = 0,
        exclude_user_id: int | None = None,
    ) -> list[GameSlot]:
        """Получить игры со свободными местами."""
        fetch_limit = limit * 2 if exclude_user_id else limit
        games = await self._execute_games_query(SQLQueries.GET_AVAILABLE_GAMES, fetch_limit, offset)

        if exclude_user_id:
            filtered_games = [game for game in games if not game.has_player(exclude_user_id)]
            return filtered_games[:limit]

        return games

    async def get_user_games(self, user_id: int, limit: int = 20, offset: int = 0) -> list[GameSlot]:
        """Получить игры пользователя."""
        return await self._execute_games_query(SQLQueries.GET_USER_GAMES, user_id, limit, offset)

    async def get_game_by_date(self, date: datetime) -> GameSlot | None:
        """Получить игру по дате."""
        async with self.get_connection() as conn:
            row = await conn.fetchrow(SQLQueries.GET_GAME_BY_DATE, date.date())

        return self._row_to_game_slot(row) if row else None

    async def get_upcoming_games_with_time(self, limit: int = 100, offset: int = 0) -> list[GameSlot]:
        """Получить предстоящие игры с указанным временем."""
        return await self._execute_games_query(SQLQueries.GET_GAMES_WITH_TIME, limit, offset)

    async def get_created_games(self, admin: int, limit: int = 20, offset: int = 0) -> list[GameSlot]:
        """Получить игры, созданные пользователем."""
        return await self._execute_games_query(SQLQueries.GET_CREATED_GAMES, admin, limit, offset)

    @database_operation(False)
    async def register_player(self, date: datetime, user_id: int) -> bool:
        """Записать игрока на игру."""
        async with self.get_connection() as conn:
            # Получить текущее состояние игры
            game = await conn.fetchrow(
                "SELECT player_1, player_2, player_3, player_4 FROM games WHERE date = $1",
                date.date(),
            )

            if not game:
                return False

            # Проверить, не записан ли игрок уже
            players = [game[f"player_{i}"] for i in range(1, 5)]
            if user_id in players:
                return False

            # Найти свободное место
            for i, player in enumerate(players, 1):
                if player is None:
                    await conn.execute(
                        f"UPDATE games SET player_{i} = $1 WHERE date = $2",  # noqa: S608
                        user_id,
                        date.date(),
                    )
                    logger.info(f"Игрок {user_id} записан на {date.date()}")
                    return True

            return False

    @database_operation(False)
    async def unregister_player(self, date: datetime, user_id: int) -> bool:
        """Отписать игрока от игры."""
        async with self.get_connection() as conn:
            game = await conn.fetchrow(
                "SELECT player_1, player_2, player_3, player_4 FROM games WHERE date = $1",
                date.date(),
            )

            if not game:
                return False

            # Найти игрока и удалить
            players = [game[f"player_{i}"] for i in range(1, 5)]
            for i, player in enumerate(players, 1):
                if player == user_id:
                    await conn.execute(
                        f"UPDATE games SET player_{i} = $1 WHERE date = $2",  # noqa: S608
                        None,
                        date.date(),
                    )
                    logger.info(f"Игрок {user_id} отписан от {date.date()}")
                    return True

            return False

    async def get_users_info(self, user_ids: list[int]) -> dict[int, str]:
        """Получить информацию о пользователях."""
        if not user_ids:
            return {}

        async with self.get_connection() as conn:
            rows = await conn.fetch(SQLQueries.GET_USERS_INFO, user_ids)

        return {row["user_id"]: self._format_user_display_name(row) for row in rows}

    async def count_available_games(self) -> int:
        """Подсчитать количество игр со свободными местами."""
        return await self._execute_count_query(SQLQueries.COUNT_AVAILABLE_GAMES)

    async def count_upcoming_games(self) -> int:
        """Подсчитать количество всех предстоящих игр."""
        return await self._execute_count_query(SQLQueries.COUNT_UPCOMING_GAMES)

    async def count_user_games(self, user_id: int) -> int:
        """Подсчитать количество игр пользователя."""
        return await self._execute_count_query(SQLQueries.COUNT_USER_GAMES, user_id)

    async def count_created_games(self, admin: int) -> int:
        """Подсчитать количество созданных пользователем игр."""
        return await self._execute_count_query(SQLQueries.COUNT_CREATED_GAMES, admin)

    async def count_available_games_excluding_user(self, user_id: int) -> int:
        """Подсчитать количество игр со свободными местами, исключая игры пользователя."""
        return await self._execute_count_query(SQLQueries.COUNT_AVAILABLE_GAMES_EXCLUDING_USER, user_id)

    async def save_user(
        self,
        user_id: int,
        username: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
    ) -> None:
        """Сохранить информацию о пользователе."""
        async with self.get_connection() as conn:
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

    @database_operation(False)
    async def create_game(  # noqa: PLR0913
        self,
        date: datetime,
        time: datetime.time,
        duration: int,
        location: str,
        court: int,
        admin: int,
    ) -> bool:
        """Создать новую игру."""
        try:
            async with self.get_connection() as conn:
                await conn.execute(
                    """
                    INSERT INTO games (date, time, duration, location, court, admin)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    ON CONFLICT (date) DO NOTHING
                    """,
                    date.date(),
                    time,
                    duration,
                    location,
                    court,
                    admin,
                )
                logger.info(f"Игра создана на {date.date()} пользователем {admin}")
                return True
        except Exception:
            logger.exception("Ошибка создания игры")
            return False

    @database_operation(False)
    async def delete_game(self, date: datetime, admin: int) -> bool:
        """Удалить игру (только создатель может удалить)."""
        try:
            async with self.get_connection() as conn:
                result = await conn.execute(
                    "DELETE FROM games WHERE date = $1 AND admin = $2",
                    date.date(),
                    admin,
                )
                success = result == "DELETE 1"
                if success:
                    logger.info(f"Игра на {date.date()} удалена пользователем {admin}")
                return success
        except Exception:
            logger.exception("Ошибка удаления игры")
            return False
