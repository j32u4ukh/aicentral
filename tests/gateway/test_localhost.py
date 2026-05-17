import pytest

from aicentral.gateway.localhost import is_loopback_host, validate_bind_host


def test_validate_bind_host_loopback() -> None:
    assert validate_bind_host("127.0.0.1") == "127.0.0.1"
    assert validate_bind_host("::1") == "::1"


def test_validate_bind_host_rejects_public() -> None:
    with pytest.raises(ValueError, match="loopback"):
        validate_bind_host("0.0.0.0")
    with pytest.raises(ValueError, match="loopback"):
        validate_bind_host("192.168.1.1")


def test_is_loopback_host() -> None:
    assert is_loopback_host("127.0.0.1")
    assert not is_loopback_host("8.8.8.8")
