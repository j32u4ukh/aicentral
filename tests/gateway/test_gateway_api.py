from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from aicentral.config.loader import load_config
from aicentral.config.schema import AICentralConfig, GatewaySettings
from aicentral.gateway.app import create_app


@pytest.fixture
def gateway_client(tmp_path: Path) -> TestClient:
    secret = tmp_path / "secret.yaml"
    secret.write_text("ollama:\n  model: x\n", encoding="utf-8")
    main = tmp_path / "aicentral.yaml"
    main.write_text(
        yaml.dump(
            {
                "gateway": {
                    "enabled": True,
                    "bind_host": "127.0.0.1",
                    "optional_token": None,
                    "reject_non_local_client": False,
                }
            }
        ),
        encoding="utf-8",
    )
    load_config(path=main, secrets_path=secret, reload=True)
    return TestClient(create_app())


def test_health(gateway_client: TestClient) -> None:
    r = gateway_client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_chat_missing_model(gateway_client: TestClient) -> None:
    r = gateway_client.post(
        "/v1/chat/completions",
        json={"model": "", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert r.status_code == 400


@patch("aicentral.gateway.routes.chat.complete")
def test_chat_non_stream(mock_complete: MagicMock, gateway_client: TestClient) -> None:
    mock_complete.return_value = "你好"
    r = gateway_client.post(
        "/v1/chat/completions",
        json={
            "model": "local-chat",
            "messages": [{"role": "user", "content": "hi"}],
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["object"] == "chat.completion"
    assert data["choices"][0]["message"]["content"] == "你好"
    mock_complete.assert_called_once()


@patch("aicentral.gateway.routes.chat.complete")
def test_chat_stream(mock_complete: MagicMock, gateway_client: TestClient) -> None:
    mock_complete.return_value = iter(["你", "好"])

    with gateway_client.stream(
        "POST",
        "/v1/chat/completions",
        json={
            "model": "local-chat",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": True,
        },
    ) as r:
        assert r.status_code == 200
        body = "".join(r.iter_text())
        assert "chat.completion.chunk" in body
        assert "[DONE]" in body


def test_optional_token(tmp_path: Path) -> None:
    secret = tmp_path / "secret.yaml"
    secret.write_text("gateway:\n  optional_token: secret-tok\n", encoding="utf-8")
    main = tmp_path / "aicentral.yaml"
    main.write_text(
        yaml.dump({"gateway": {"optional_token": None, "reject_non_local_client": False}}),
        encoding="utf-8",
    )
    load_config(path=main, secrets_path=secret, reload=True)
    client = TestClient(create_app())

    r = client.post(
        "/v1/chat/completions",
        json={"model": "m", "messages": [{"role": "user", "content": "x"}]},
    )
    assert r.status_code == 401

    with patch("aicentral.gateway.routes.chat.complete", return_value="ok"):
        r2 = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer secret-tok"},
            json={"model": "m", "messages": [{"role": "user", "content": "x"}]},
        )
        assert r2.status_code == 200


def test_convert_rejects_remote_image_without_fetch() -> None:
    from aicentral.gateway.convert import ContentValidationError, messages_to_internal
    from aicentral.gateway.schemas import ChatMessageIn

    gw = GatewaySettings(fetch_remote_images=False)
    msgs = [
        ChatMessageIn(
            role="user",
            content=[
                {
                    "type": "image_url",
                    "image_url": {"url": "https://example.com/x.jpg"},
                }
            ],
        )
    ]
    with pytest.raises(ContentValidationError, match="fetch_remote_images"):
        messages_to_internal(msgs, gw)
