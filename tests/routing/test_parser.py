import pytest

from aicentral.exceptions import ProviderError
from aicentral.routing.parser import DEFAULT_PROVIDER, parse_model


def test_parse_model_bare_name() -> None:
    parsed = parse_model("gemma4:e2b")
    assert parsed == (DEFAULT_PROVIDER, "gemma4:e2b")


def test_parse_model_with_provider() -> None:
    parsed = parse_model("ollama/gemma4:e2b")
    assert parsed == ("ollama", "gemma4:e2b")


def test_parse_model_none_uses_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_MODEL", "from-env")
    parsed = parse_model(None)
    assert parsed == (DEFAULT_PROVIDER, "from-env")


def test_parse_model_invalid_raises() -> None:
    with pytest.raises(ValueError):
        parse_model("ollama/")


def test_complete_unknown_provider() -> None:
    from aicentral import complete

    with pytest.raises(ProviderError, match="未知 provider"):
        complete(
            messages=[{"role": "user", "content": "hi"}],
            model="unknown/foo",
        )
