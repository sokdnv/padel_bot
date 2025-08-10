"""Стандартизированные ответы сервисов."""

from dataclasses import dataclass
from typing import Any


@dataclass
class ServiceResponse:
    """Стандартный ответ сервиса."""
    
    success: bool
    message: str = ""
    data: dict[str, Any] | None = None
    alert: bool = True
    
    @classmethod
    def success_response(cls, message: str = "", data: dict[str, Any] | None = None, alert: bool = False) -> "ServiceResponse":
        """Создать успешный ответ."""
        return cls(success=True, message=message, data=data, alert=alert)
    
    @classmethod
    def error_response(cls, message: str, alert: bool = True, data: dict[str, Any] | None = None) -> "ServiceResponse":
        """Создать ответ с ошибкой."""
        return cls(success=False, message=message, alert=alert, data=data)
    
    def to_dict(self) -> dict[str, Any]:
        """Конвертировать в словарь для обратной совместимости."""
        result = {
            "success": self.success,
            "message": self.message,
            "alert": self.alert,
        }
        if self.data:
            result.update(self.data)
        return result