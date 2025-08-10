"""Декораторы для обработки ошибок и логирования."""

import functools
from typing import Any, Callable

from src.config import logger
from src.shared.responses import ServiceResponse


def handle_service_errors(default_message: str = "Произошла ошибка") -> Callable:
    """Декоратор для обработки ошибок в сервисах."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> ServiceResponse:
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                logger.error(f"Ошибка в {func.__name__}: {e}")
                return ServiceResponse.error_response(default_message)
        return wrapper
    return decorator


def log_handler_calls(func: Callable) -> Callable:
    """Декоратор для логирования вызовов обработчиков."""
    @functools.wraps(func)
    async def wrapper(*args, **kwargs) -> Any:
        handler_name = func.__name__
        logger.debug(f"Обработчик {handler_name} вызван")
        try:
            result = await func(*args, **kwargs)
            logger.debug(f"Обработчик {handler_name} выполнен успешно")
            return result
        except Exception as e:
            logger.error(f"Ошибка в обработчике {handler_name}: {e}")
            raise
    return wrapper


def database_operation(default_result: Any = None) -> Callable:
    """Декоратор для безопасных операций с базой данных."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                logger.error(f"Ошибка БД в {func.__name__}: {e}")
                return default_result
        return wrapper
    return decorator