"""gemini_headers 解析測試。"""

from aicentral.routing.gemini_headers import (
    parse_rate_limit_from_response,
    parse_rate_limit_headers,
)


def test_parse_x_ratelimit_headers() -> None:
    info = parse_rate_limit_headers(
        {
            "x-ratelimit-limit-requests": "15",
            "x-ratelimit-remaining-requests": "3",
            "x-ratelimit-reset-requests": "2026-05-24T12:01:00Z",
        }
    )
    assert info.limit_requests == 15
    assert info.remaining_requests == 3
    assert info.reset_requests == "2026-05-24T12:01:00Z"


def test_parse_429_retry_after_header() -> None:
    info = parse_rate_limit_from_response(
        {"retry-after": "30"},
        status_code=429,
        body="",
    )
    assert info.retry_after_seconds == 30.0
    assert info.remaining_requests == 0


def test_parse_429_retry_delay_in_json_body() -> None:
    body = """{
      "error": {
        "code": 429,
        "status": "RESOURCE_EXHAUSTED",
        "details": [{"retryDelay": "12s"}]
      }
    }"""
    info = parse_rate_limit_from_response({}, status_code=429, body=body)
    assert info.retry_after_seconds == 12.0
