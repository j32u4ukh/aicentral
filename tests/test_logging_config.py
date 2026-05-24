"""套件日誌：NullHandler 與 configure_logging。"""

from __future__ import annotations

import io
import logging

import pytest

from aicentral.logging_config import PACKAGE_LOGGER_NAME, configure_logging, ensure_package_logging


def test_import_registers_null_handler_and_no_propagate() -> None:
    logger = logging.getLogger(PACKAGE_LOGGER_NAME)
    assert any(isinstance(h, logging.NullHandler) for h in logger.handlers)
    assert logger.propagate is False


def test_ensure_package_logging_idempotent() -> None:
    logger = ensure_package_logging()
    handler_count = len(logger.handlers)
    ensure_package_logging()
    assert len(logger.handlers) == handler_count


def test_configure_logging_enables_propagation_and_output() -> None:
    buf = io.StringIO()
    configure_logging(level=logging.INFO, force=True, stream=buf)
    pkg = logging.getLogger(PACKAGE_LOGGER_NAME)
    assert pkg.propagate is True

    logging.getLogger("aicentral.history").info("test-history-log-line")
    assert "test-history-log-line" in buf.getvalue()


def test_library_logger_quiet_without_configure(caplog: pytest.LogCaptureFixture) -> None:
    """未 configure 時，子 logger 訊息不應出現在 caplog。"""
    pkg = logging.getLogger(PACKAGE_LOGGER_NAME)
    pkg.handlers.clear()
    pkg.addHandler(logging.NullHandler())
    pkg.propagate = False

    history = logging.getLogger("aicentral.history")
    with caplog.at_level(logging.INFO, logger="aicentral.history"):
        history.info("should-not-appear-quiet")
    assert not any("should-not-appear-quiet" in r.message for r in caplog.records)
