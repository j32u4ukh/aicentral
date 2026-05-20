"""對外 OpenAI Chat Completions 請求/回應（子集）。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from aicentral.config.schema import MCPServerEntry


class TextPart(BaseModel):
    type: Literal["text"] = "text"
    text: str


class ImageUrlDetail(BaseModel):
    url: str
    detail: str | None = None


class ImageUrlPart(BaseModel):
    type: Literal["image_url"] = "image_url"
    image_url: ImageUrlDetail


class ChatMessageIn(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str | list[dict[str, Any]]


class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[ChatMessageIn]
    stream: bool = False
    temperature: float | None = None
    max_tokens: int | None = None


class ChatCompletionChoice(BaseModel):
    index: int = 0
    message: dict[str, Any]
    finish_reason: str = "stop"


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[ChatCompletionChoice]
    usage: dict[str, int] = Field(
        default_factory=lambda: {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }
    )


# --- MCP Gateway (v0.6.1) ---


class MCPServerRegisterBody(BaseModel):
    """POST/PUT 單一 server；``auth_value`` 僅接受於請求，不回傳於 GET。"""

    name: str = Field(..., min_length=1)
    transport: str
    url: str | None = None
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    auth_type: str = "none"
    auth_value: str | None = None
    description: str | None = None
    timeout: float | None = None
    allowed_tools: list[str] | None = None
    disallowed_tools: list[str] | None = None
    static_headers: dict[str, str] = Field(default_factory=dict)

    def to_entry(self) -> MCPServerEntry:
        return MCPServerEntry.model_validate(
            self.model_dump(exclude={"name"}, exclude_none=False)
        )


class MCPServersBatchBody(BaseModel):
    servers: dict[str, dict[str, Any]]


class MCPServerListResponse(BaseModel):
    servers: list[dict[str, Any]]


class MCPToolsListResponse(BaseModel):
    tools: list[dict[str, Any]]


class MCPToolCallBody(BaseModel):
    arguments: dict[str, Any] = Field(default_factory=dict)


class MCPToolCallResponse(BaseModel):
    result: Any
