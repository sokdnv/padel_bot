"""Скрипт с классом с запросами в базу."""


class SQLQueries:
    """Константы SQL запросов."""

    # Game selection fields
    GAME_FIELDS = """
        date, player_1, player_2, player_3, player_4,
        time, duration, location, court, admin
    """

    # User fields
    USER_FIELDS = "user_id, username, first_name, last_name"

    # Common WHERE conditions
    FUTURE_GAMES = "date >= CURRENT_DATE"
    AVAILABLE_SLOTS = """
        (player_1 IS NULL OR player_2 IS NULL OR player_3 IS NULL OR player_4 IS NULL)
    """
    TIME_CONDITIONS = """
        (time IS NULL OR (date > CURRENT_DATE OR (date = CURRENT_DATE AND time > CURRENT_TIME)))
    """

    # Complete queries
    GET_UPCOMING_GAMES = f"""
        SELECT {GAME_FIELDS}
        FROM games
        WHERE {FUTURE_GAMES}
        ORDER BY date
        LIMIT $1 OFFSET $2
    """  # noqa: S608

    GET_AVAILABLE_GAMES = f"""
        SELECT {GAME_FIELDS}
        FROM games
        WHERE {FUTURE_GAMES}
          AND {AVAILABLE_SLOTS}
          AND {TIME_CONDITIONS}
        ORDER BY date
        LIMIT $1 OFFSET $2
    """  # noqa: S608

    GET_USER_GAMES = f"""
        SELECT {GAME_FIELDS}
        FROM games
        WHERE date >= CURRENT_DATE - INTERVAL '1 day'
          AND (player_1 = $1 OR player_2 = $1 OR player_3 = $1 OR player_4 = $1)
          AND {TIME_CONDITIONS}
        ORDER BY date
        LIMIT $2 OFFSET $3
    """  # noqa: S608

    GET_GAME_BY_DATE = f"""
        SELECT {GAME_FIELDS}
        FROM games
        WHERE date = $1
    """  # noqa: S608

    GET_USERS_INFO = f"""
        SELECT {USER_FIELDS}
        FROM users
        WHERE user_id = ANY($1)
    """  # noqa: S608

    COUNT_AVAILABLE_GAMES = f"""
        SELECT COUNT(*) FROM games
        WHERE {FUTURE_GAMES}
          AND {AVAILABLE_SLOTS}
          AND {TIME_CONDITIONS}
    """  # noqa: S608

    COUNT_USER_GAMES = f"""
        SELECT COUNT(*) FROM games
        WHERE date >= CURRENT_DATE - INTERVAL '1 day'
          AND (player_1 = $1 OR player_2 = $1 OR player_3 = $1 OR player_4 = $1)
          AND {TIME_CONDITIONS}
    """  # noqa: S608

    GET_GAMES_WITH_TIME = f"""
        SELECT {GAME_FIELDS}
        FROM games
        WHERE {FUTURE_GAMES}
          AND time IS NOT NULL
        ORDER BY date, time
        LIMIT $1 OFFSET $2
    """  # noqa: S608

    GET_CREATED_GAMES = f"""
        SELECT {GAME_FIELDS}
        FROM games
        WHERE admin = $1 AND {FUTURE_GAMES}
        ORDER BY date
        LIMIT $2 OFFSET $3
    """  # noqa: S608

    COUNT_CREATED_GAMES = f"""
        SELECT COUNT(*) FROM games
        WHERE admin = $1 AND {FUTURE_GAMES}
    """  # noqa: S608

    COUNT_UPCOMING_GAMES = f"""
        SELECT COUNT(*) FROM games
        WHERE {FUTURE_GAMES}
    """  # noqa: S608

    COUNT_AVAILABLE_GAMES_EXCLUDING_USER = f"""
        SELECT COUNT(*) FROM games
        WHERE {FUTURE_GAMES}
          AND {AVAILABLE_SLOTS}
          AND {TIME_CONDITIONS}
          AND NOT (player_1 = $1 OR player_2 = $1 OR player_3 = $1 OR player_4 = $1)
    """  # noqa: S608
