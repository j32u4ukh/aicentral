"""effective_embedding_model 解析。"""

from aicentral.config.schema import AICentralConfig, DefaultsSettings
from aicentral.routing.router import effective_embedding_model


def test_explicit_embedding_model() -> None:
    assert effective_embedding_model("my-embed") == "my-embed"


def test_defaults_embedding_model() -> None:
    cfg = AICentralConfig(defaults=DefaultsSettings(embedding_model="local-embed"))
    assert effective_embedding_model(None, config=cfg) == "local-embed"


def test_fallback_local_embed() -> None:
    cfg = AICentralConfig(defaults=DefaultsSettings())
    assert effective_embedding_model(None, config=cfg) == "local-embed"
