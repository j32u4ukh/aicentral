"""aicentral 例外（v0.1 精簡版，v0.2 移至 core/errors.py）。"""


class AICentralError(Exception):
    """aicentral 基底例外。"""


class ProviderError(AICentralError):
    """Provider HTTP 或回應格式錯誤。"""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
