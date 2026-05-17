"""aicentral 例外。"""


class AICentralError(Exception):
    """aicentral 基底例外。"""


class ProviderError(AICentralError):
    """Provider HTTP 或回應格式錯誤。"""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class HistoryOverflowError(AICentralError):
    """有狀態 Chat 在 manual 策略下歷史超過 max_messages。"""
