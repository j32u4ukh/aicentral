from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel

from aicentral import complete_structured
from aicentral.core.dev import is_dev_mode
from aicentral.core.errors import StructuredNoPayloadError


class Ticket(BaseModel):
    title: str
    priority: int


def test_is_dev_mode_false_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AICENTRAL_DEV", raising=False)
    assert is_dev_mode() is False


def test_is_dev_mode_true(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AICENTRAL_DEV", "1")
    assert is_dev_mode() is True


@patch("aicentral.core.client.invoke_resolved")
def test_structured_error_includes_assistant_summary(mock_invoke: MagicMock) -> None:
    mock_invoke.return_value = {
        "choices": [{"message": {"role": "assistant", "content": "你好"}}]
    }

    with pytest.raises(StructuredNoPayloadError) as exc_info:
        complete_structured(
            messages=[{"role": "user", "content": "hi"}],
            response_model=Ticket,
        )

    err = exc_info.value
    assert err.failure_kind.value == "no_payload"
    assert "content=" in (err.assistant_summary or "")
    assert "你好" in str(err)
