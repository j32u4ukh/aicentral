"""開發模式：將除錯資訊輸出至終端機（stderr）。"""

from __future__ import annotations

import os
import sys
from typing import Any


def is_dev_mode() -> bool:
    """是否啟用開發模式（``AICENTRAL_DEV=1`` / ``true`` / ``yes``）。"""
    value = os.getenv("AICENTRAL_DEV", "").strip().lower()
    return value in ("1", "true", "yes", "on")


def dev_print(*parts: Any, sep: str = " ", end: str = "\n") -> None:
    """開發模式下寫入 stderr；一般模式不輸出。"""
    if not is_dev_mode():
        return
    print("[aicentral dev]", *parts, sep=sep, end=end, file=sys.stderr)


def dev_print_exception(exc: BaseException, *, context: str | None = None) -> None:
    """開發模式下印出例外與可選情境說明。"""
    if not is_dev_mode():
        return
    if context:
        dev_print(context)
    dev_print(type(exc).__name__ + ":", exc)
