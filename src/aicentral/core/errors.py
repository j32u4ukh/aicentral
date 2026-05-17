"""aicentral 例外。"""

from __future__ import annotations

from pydantic import BaseModel


class AICentralError(Exception):
    """aicentral 基底例外。"""


class ProviderError(AICentralError):
    """Provider HTTP 或回應格式錯誤。"""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class HistoryOverflowError(AICentralError):
    """有狀態 Chat 在 manual 策略下歷史超過 max_messages。"""


class StructuredOutputError(AICentralError):
    """結構化輸出在重試用盡後仍無法得到合法的 ``response_model``。"""

    def __init__(
        self,
        message: str,
        *,
        response_model: type[BaseModel],
        attempts: int,
        last_validation_error: str | None = None,
    ) -> None:
        super().__init__(message)
        self.response_model = response_model
        self.attempts = attempts
        self.last_validation_error = last_validation_error
