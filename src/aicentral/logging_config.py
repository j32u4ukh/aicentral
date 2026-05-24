"""aicentral 套件日誌：library 預設安靜，應用／CLI 入口呼叫 ``configure_logging``。

import 時對 ``aicentral`` logger 掛 ``NullHandler`` 且 ``propagate=False``，
避免未設定 logging 時出現「No handler」警告或意外寫入 stderr。
CLI、Gateway、示範腳本應在 ``main`` 開頭呼叫 ``configure_logging()``。
"""

from __future__ import annotations

import logging
import sys
from typing import TextIO

PACKAGE_LOGGER_NAME = "aicentral"
_DEFAULT_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
_DEFAULT_DATEFMT = "%H:%M:%S"


def ensure_package_logging(
    *,
    logger_name: str = PACKAGE_LOGGER_NAME,
) -> logging.Logger:
    """套件載入時：無 handler 則掛 NullHandler，並關閉向 root 傳播。"""
    logger = logging.getLogger(logger_name)
    if not logger.handlers:
        logger.addHandler(logging.NullHandler())
    logger.propagate = False
    return logger


def configure_logging(
    *,
    level: int | str = logging.INFO,
    fmt: str = _DEFAULT_FORMAT,
    datefmt: str = _DEFAULT_DATEFMT,
    stream: TextIO | None = None,
    package_logger_name: str = PACKAGE_LOGGER_NAME,
    logger_names: list[str] | None = None,
    force: bool = True,
) -> logging.Logger:
    """應用／CLI：``basicConfig`` 並讓套件 logger 訊息傳至 root。

    ``logger_names`` 可額外設定子 logger 最低等級（例如 ``["aicentral.history"]``）。
    回傳 ``package_logger_name`` 對應的 logger。
    """
    out = stream if stream is not None else sys.stderr
    logging.basicConfig(
        level=level,
        format=fmt,
        datefmt=datefmt,
        stream=out,
        force=force,
    )
    pkg = logging.getLogger(package_logger_name)
    pkg.propagate = True
    pkg.setLevel(level)
    for name in logger_names or []:
        logging.getLogger(name).setLevel(level)
    return pkg
