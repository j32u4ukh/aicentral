"""Gemini HTTP 限流標頭與 429 回應解析（gemini-limit.md 方案三）。"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Mapping

logger = logging.getLogger(__name__)

_RETRY_AFTER_RE = re.compile(r"^(\d+(?:\.\d+)?)\s*s?$", re.IGNORECASE)


@dataclass(frozen=True)
class GeminiRateLimitInfo:
    """從 Response Header（或 429 body）解析出的配額快照。"""

    limit_requests: int | None = None
    remaining_requests: int | None = None
    reset_requests: str | None = None
    retry_after_seconds: float | None = None


def _header_get(headers: Mapping[str, str], name: str) -> str | None:
    lower = name.lower()
    for key, value in headers.items():
        if key.lower() == lower:
            return value.strip() if value else None
    return None


def _parse_int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def _parse_retry_after_value(value: str | None) -> float | None:
    if not value:
        return None
    value = value.strip()
    try:
        return float(value)
    except ValueError:
        pass
    match = _RETRY_AFTER_RE.match(value)
    if match:
        return float(match.group(1))
    return None


def _retry_from_error_json(body: str) -> float | None:
    """Google RPC 錯誤 JSON 內的 retryDelay（如 ``34s``）。"""
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    error = data.get("error")
    if not isinstance(error, dict):
        return None
    details = error.get("details")
    if not isinstance(details, list):
        return None
    for item in details:
        if not isinstance(item, dict):
            continue
        retry = item.get("retryDelay") or item.get("retry_delay")
        if isinstance(retry, str):
            parsed = _parse_retry_after_value(retry)
            if parsed is not None:
                return parsed
        if isinstance(retry, (int, float)):
            return float(retry)
    return None


def parse_rate_limit_headers(headers: Mapping[str, str]) -> GeminiRateLimitInfo:
    """
    解析常見限流標頭（含 x-ratelimit-* 與 retry-after）。

    參考 gemini-limit.md 方案三；若 API 未回傳則各欄位為 None。
    """
    limit_req = _parse_int(_header_get(headers, "x-ratelimit-limit-requests"))
    remaining = _parse_int(_header_get(headers, "x-ratelimit-remaining-requests"))
    reset_at = _header_get(headers, "x-ratelimit-reset-requests") or _header_get(
        headers, "x-ratelimit-reset"
    )
    retry_after = _parse_retry_after_value(_header_get(headers, "retry-after"))
    return GeminiRateLimitInfo(
        limit_requests=limit_req,
        remaining_requests=remaining,
        reset_requests=reset_at,
        retry_after_seconds=retry_after,
    )


def parse_rate_limit_from_response(
    headers: Mapping[str, str],
    *,
    status_code: int,
    body: str = "",
) -> GeminiRateLimitInfo:
    """合併 header 與 429 body 的 retry 資訊。"""
    info = parse_rate_limit_headers(headers)
    if status_code == 429:
        body_retry = _retry_from_error_json(body)
        retry = body_retry if body_retry is not None else info.retry_after_seconds
        return GeminiRateLimitInfo(
            limit_requests=info.limit_requests,
            remaining_requests=info.remaining_requests if info.remaining_requests is not None else 0,
            reset_requests=info.reset_requests,
            retry_after_seconds=retry,
        )
    return info


def log_rate_limit_info(model_id: str, info: GeminiRateLimitInfo) -> None:
    """開發時可見的配額快照（方案三：從 Header 得知剩餘次數）。"""
    parts: list[str] = []
    if info.remaining_requests is not None:
        parts.append(f"remaining={info.remaining_requests}")
    if info.limit_requests is not None:
        parts.append(f"limit={info.limit_requests}")
    if info.reset_requests:
        parts.append(f"reset={info.reset_requests}")
    if info.retry_after_seconds is not None:
        parts.append(f"retry_after={info.retry_after_seconds}s")
    if parts:
        logger.info("Gemini %s 配額標頭: %s", model_id, ", ".join(parts))
