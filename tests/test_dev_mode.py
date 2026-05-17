from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml
from pydantic import BaseModel

from aicentral import complete_structured
from aicentral.config.loader import load_config
from aicentral.core.dev import is_dev_mode
from aicentral.core.errors import StructuredNoPayloadError


class Ticket(BaseModel):
    title: str
    priority: int


def test_is_dev_mode_false_by_default() -> None:
    from aicentral.config.loader import repo_root

    load_config(
        path=repo_root() / "config" / "aicentral.yaml",
        secrets_path=repo_root() / "config" / "secret.yaml",
        reload=True,
    )
    assert is_dev_mode() is False


def test_is_dev_mode_true(tmp_path: Path) -> None:
    main = tmp_path / "aicentral.yaml"
    main.write_text(
        yaml.dump({"aicentral_settings": {"dev": True}}),
        encoding="utf-8",
    )
    secret = tmp_path / "secret.yaml"
    secret.write_text("ollama:\n  model: x\n", encoding="utf-8")
    load_config(path=main, secrets_path=secret, reload=True)
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
