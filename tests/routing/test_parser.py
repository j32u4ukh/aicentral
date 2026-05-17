from pathlib import Path

import pytest

from aicentral.exceptions import ProviderError
from aicentral.routing.parser import DEFAULT_PROVIDER, parse_model


def test_parse_model_bare_name() -> None:
    parsed = parse_model("gemma4:e2b")
    assert parsed == (DEFAULT_PROVIDER, "gemma4:e2b")


def test_parse_model_with_provider() -> None:
    parsed = parse_model("ollama/gemma4:e2b")
    assert parsed == ("ollama", "gemma4:e2b")


def test_parse_model_none_uses_secret_yaml(tmp_path: Path) -> None:
    from aicentral.config.loader import load_config

    secret = tmp_path / "secret.yaml"
    secret.write_text("ollama:\n  model: from-secret\n", encoding="utf-8")
    load_config(path=tmp_path / "x.yaml", secrets_path=secret, reload=True)
    parsed = parse_model(None)
    assert parsed == (DEFAULT_PROVIDER, "from-secret")


def test_parse_model_invalid_raises() -> None:
    with pytest.raises(ValueError):
        parse_model("ollama/")


def test_parse_model_unknown_provider_raises() -> None:
    with pytest.raises(ValueError, match="未知 provider"):
        parse_model("unknown/foo")


def test_complete_unknown_provider() -> None:
    from aicentral import complete

    with pytest.raises(ProviderError, match="未知 provider"):
        complete(
            messages=[{"role": "user", "content": "hi"}],
            model="unknown/foo",
        )
