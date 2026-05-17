"""OpenAI JSON ↔ aicentral Message；SSE chunk 組裝。"""

from __future__ import annotations

import base64
import re
import time
import uuid
from typing import Any

from aicentral.config.schema import GatewaySettings
from aicentral.core.types import Message
from aicentral.gateway.schemas import ChatCompletionRequest, ChatMessageIn

_UNSUPPORTED_PART_TYPES = frozenset({"input_audio", "file"})
_DATA_URL_RE = re.compile(r"^data:(image/[^;]+);base64,(.+)$", re.DOTALL)


class ContentValidationError(ValueError):
    pass


def messages_to_internal(
    messages: list[ChatMessageIn],
    gw: GatewaySettings,
) -> list[Message]:
    internal: list[Message] = []
    for msg in messages:
        content = _normalize_content(msg.content, gw)
        internal.append({"role": msg.role, "content": content})
    return internal


def _normalize_content(
    content: str | list[dict[str, Any]],
    gw: GatewaySettings,
) -> str | list[dict[str, Any]]:
    if isinstance(content, str):
        return content
    parts: list[dict[str, Any]] = []
    for part in content:
        if not isinstance(part, dict):
            raise ContentValidationError("content part 須為 object")
        ptype = part.get("type")
        if ptype in _UNSUPPORTED_PART_TYPES:
            raise ContentValidationError(f"不支援的 content type: {ptype}")
        if ptype == "text":
            parts.append({"type": "text", "text": str(part.get("text", ""))})
        elif ptype == "image_url":
            img = part.get("image_url")
            if not isinstance(img, dict):
                raise ContentValidationError("image_url 須為 object")
            url = str(img.get("url", "")).strip()
            if not url:
                raise ContentValidationError("image_url.url 不可為空")
            normalized = _normalize_image_url(url, gw)
            detail = img.get("detail")
            entry: dict[str, Any] = {"type": "image_url", "image_url": {"url": normalized}}
            if detail is not None:
                entry["image_url"]["detail"] = detail
            parts.append(entry)
        else:
            raise ContentValidationError(f"不支援的 content type: {ptype}")
    if not parts:
        raise ContentValidationError("content parts 不可為空")
    return parts


def _normalize_image_url(url: str, gw: GatewaySettings) -> str:
    if url.startswith("data:"):
        match = _DATA_URL_RE.match(url)
        if not match:
            raise ContentValidationError("無效的 data URL")
        mime, b64 = match.group(1), match.group(2)
        if mime not in gw.allowed_image_mime:
            raise ContentValidationError(f"不允許的圖片 MIME: {mime}")
        try:
            raw = base64.b64decode(b64, validate=True)
        except Exception as exc:
            raise ContentValidationError("base64 解碼失敗") from exc
        if len(raw) > gw.max_image_bytes:
            raise ContentValidationError("圖片超過 max_image_bytes")
        return url
    if url.startswith(("http://", "https://")):
        if not gw.fetch_remote_images:
            raise ContentValidationError(
                "遠端圖片 URL 已停用（fetch_remote_images=false）；請使用 base64 data URL"
            )
        return url
    raise ContentValidationError("image_url 須為 data URL 或 http(s) URL")


def build_completion_response(*, model: str, content: str) -> dict[str, Any]:
    return {
        "id": f"chatcmpl-ac-{uuid.uuid4().hex[:24]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def build_stream_chunk(*, model: str, delta_content: str, chunk_id: str) -> dict[str, Any]:
    return {
        "id": chunk_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "delta": {"content": delta_content}, "finish_reason": None}],
    }


def extract_completion_kwargs(req: ChatCompletionRequest) -> dict[str, Any]:
    extra: dict[str, Any] = {}
    if req.temperature is not None:
        extra["temperature"] = req.temperature
    if req.max_tokens is not None:
        extra["max_tokens"] = req.max_tokens
    return extra
