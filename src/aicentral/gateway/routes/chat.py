"""POST /v1/chat/completions"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, StreamingResponse

from aicentral.config import get_config
from aicentral.core.client import complete
from aicentral.core.errors import ProviderError
from aicentral.gateway.auth import verify_optional_bearer
from aicentral.gateway.convert import (
    ContentValidationError,
    build_completion_response,
    build_stream_chunk,
    extract_completion_kwargs,
    messages_to_internal,
)
from aicentral.gateway.errors import openai_error_response, provider_error_response
from aicentral.gateway.schemas import ChatCompletionRequest

router = APIRouter()


@router.post("/v1/chat/completions", response_model=None)
def chat_completions(
    body: ChatCompletionRequest,
    _: None = Depends(verify_optional_bearer),
):
    gw = get_config().gateway
    model = (body.model or "").strip()
    if not model:
        return openai_error_response("缺少 model", status_code=400)

    try:
        messages = messages_to_internal(body.messages, gw)
    except ContentValidationError as exc:
        return openai_error_response(str(exc), status_code=400)

    extra = extract_completion_kwargs(body)

    if body.stream:
        return _stream_response(model, messages, extra)

    try:
        text = complete(messages, model, stream=False, **extra)
    except ProviderError as exc:
        return provider_error_response(exc)
    except ValueError as exc:
        return openai_error_response(str(exc), status_code=400)

    if not isinstance(text, str):
        return openai_error_response("內部錯誤：非串流回傳型別異常", status_code=500)

    return JSONResponse(content=build_completion_response(model=model, content=text))


def _stream_response(
    model: str,
    messages: list,
    extra: dict,
) -> StreamingResponse:
    chunk_id = f"chatcmpl-ac-{uuid.uuid4().hex[:24]}"

    def generate() -> Iterator[str]:
        try:
            stream = complete(messages, model, stream=True, **extra)
            if not isinstance(stream, Iterator):
                err = {"error": {"message": "內部錯誤", "type": "api_error", "code": None}}
                yield f"data: {json.dumps(err, ensure_ascii=False)}\n\n"
                return
            for delta in stream:
                payload = build_stream_chunk(
                    model=model, delta_content=delta, chunk_id=chunk_id
                )
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        except ProviderError as exc:
            err = {
                "error": {
                    "message": str(exc),
                    "type": "api_error",
                    "code": None,
                }
            }
            yield f"data: {json.dumps(err, ensure_ascii=False)}\n\n"
        except ValueError as exc:
            err = {
                "error": {
                    "message": str(exc),
                    "type": "invalid_request_error",
                    "code": None,
                }
            }
            yield f"data: {json.dumps(err, ensure_ascii=False)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
