"""aicentral 例外。"""

from __future__ import annotations

from enum import StrEnum

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


class StructuredFailureKind(StrEnum):
    """結構化單次失敗原因（供消費方分支處理）。"""

    NO_PAYLOAD = "no_payload"
    VALIDATION = "validation"


class StructuredOutputError(AICentralError):
    """結構化輸出失敗（基底）。"""

    def __init__(
        self,
        message: str,
        *,
        response_model: type[BaseModel],
        failure_kind: StructuredFailureKind,
        validation_detail: str | None = None,
        assistant_summary: str | None = None,
        structured_mode: str | None = None,
    ) -> None:
        super().__init__(message)
        self.response_model = response_model
        self.failure_kind = failure_kind
        self.validation_detail = validation_detail
        self.assistant_summary = assistant_summary
        self.structured_mode = structured_mode

    def __str__(self) -> str:
        lines = [self.args[0] if self.args else ""]
        if self.structured_mode:
            lines.append(f"結構化模式: {self.structured_mode}")
        lines.append(f"失敗類型: {self.failure_kind}")
        if self.assistant_summary:
            lines.append(f"模型回覆: {self.assistant_summary}")
        if self.validation_detail:
            lines.append(f"驗證: {self.validation_detail}")
        if self.structured_mode == "tool" and self.failure_kind == StructuredFailureKind.NO_PAYLOAD:
            lines.append(
                "  提示: 可設 AICENTRAL_STRUCTURED_MODE=json "
                "或 complete_structured(..., mode='json')。"
            )
        return "\n".join(line for line in lines if line)


class StructuredNoPayloadError(StructuredOutputError):
    """模型未回傳可解析的結構化內容（無 tool_calls / 無有效 JSON）。"""

    def __init__(
        self,
        message: str,
        *,
        response_model: type[BaseModel],
        assistant_summary: str | None = None,
        structured_mode: str | None = None,
    ) -> None:
        super().__init__(
            message,
            response_model=response_model,
            failure_kind=StructuredFailureKind.NO_PAYLOAD,
            assistant_summary=assistant_summary,
            structured_mode=structured_mode,
        )


class StructuredValidationError(StructuredOutputError):
    """模型有回傳 JSON，但未通過 ``response_model`` 驗證。"""

    def __init__(
        self,
        message: str,
        *,
        response_model: type[BaseModel],
        validation_detail: str,
        assistant_summary: str | None = None,
        structured_mode: str | None = None,
    ) -> None:
        super().__init__(
            message,
            response_model=response_model,
            failure_kind=StructuredFailureKind.VALIDATION,
            validation_detail=validation_detail,
            assistant_summary=assistant_summary,
            structured_mode=structured_mode,
        )
