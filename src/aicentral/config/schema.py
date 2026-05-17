"""aicentral v4.0 設定檔 Pydantic schema。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ProviderName = Literal["ollama", "openai", "anthropic", "gemini"]
MCPTransportName = Literal["stdio", "http", "sse"]
MCPAuthName = Literal[
    "none",
    "api_key",
    "bearer_token",
    "basic",
    "authorization",
]
FallbackOnKind = Literal["connection_error", "timeout"]


class ModelParams(BaseModel):
    model_id: str
    api_base: str | None = None
    api_key: str | None = None
    api_version: str | None = None


class ModelEntry(BaseModel):
    model_name: str
    provider: ProviderName
    params: ModelParams
    timeout: float | None = None
    stream_timeout: float | None = None


class FallbackEntry(BaseModel):
    model_name: str
    fallbacks: list[str] = Field(default_factory=list)


class RouterSettings(BaseModel):
    fallbacks: list[FallbackEntry] = Field(default_factory=list)
    fallback_on: list[FallbackOnKind] = Field(
        default_factory=lambda: ["connection_error", "timeout"]
    )


class MCPServerEntry(BaseModel):
    transport: MCPTransportName
    url: str | None = None
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    auth_type: MCPAuthName = "none"
    auth_value: str | None = None
    description: str | None = None
    timeout: float | None = None
    allowed_tools: list[str] | None = None
    disallowed_tools: list[str] | None = None
    static_headers: dict[str, str] = Field(default_factory=dict)


class MCPSettings(BaseModel):
    tool_name_prefix: bool = True
    client_timeout: float = 30.0
    allowed_servers: list[str] | None = None


class AICentralSettings(BaseModel):
    dev: bool = False
    system_prompt: str | None = None
    drop_unsupported_params: bool = True


class DefaultsSettings(BaseModel):
    model: str | None = None
    timeout: float = 120.0
    structured_mode: str | None = None


class AppSettings(BaseModel):
    """應用層執行環境（供消費方或日後 gateway 參考；庫核心不依賴）。"""

    env: str = "development"
    log_level: str = "INFO"


class GatewaySettings(BaseModel):
    """v5.0 HTTP Gateway（僅 localhost）。"""

    enabled: bool = False
    bind_host: str = "127.0.0.1"
    bind_port: int = 8080
    localhost_only: bool = True
    reject_non_local_client: bool = True
    max_body_bytes: int = 20_971_520
    max_image_bytes: int = 10_485_760
    allowed_image_mime: list[str] = Field(
        default_factory=lambda: ["image/jpeg", "image/png", "image/webp", "image/gif"]
    )
    fetch_remote_images: bool = False
    optional_token: str | None = None
    default_model: str | None = None


class AICentralConfig(BaseModel):
    app: AppSettings = Field(default_factory=AppSettings)
    gateway: GatewaySettings = Field(default_factory=GatewaySettings)
    defaults: DefaultsSettings = Field(default_factory=DefaultsSettings)
    model_list: list[ModelEntry] = Field(default_factory=list)
    router: RouterSettings = Field(default_factory=RouterSettings)
    mcp_servers: dict[str, MCPServerEntry] = Field(default_factory=dict)
    mcp_settings: MCPSettings = Field(default_factory=MCPSettings)
    aicentral_settings: AICentralSettings = Field(default_factory=AICentralSettings)

    def model_entry_by_name(self, name: str) -> ModelEntry | None:
        key = name.strip()
        for entry in self.model_list:
            if entry.model_name == key:
                return entry
        return None

    def fallback_chain(self, model_name: str) -> list[str]:
        for entry in self.router.fallbacks:
            if entry.model_name == model_name:
                return [model_name, *entry.fallbacks]
        return [model_name]
