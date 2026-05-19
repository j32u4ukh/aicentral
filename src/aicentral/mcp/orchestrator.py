"""MCP 工具編排 — 在 LLM 與 ``MCPManager`` 之間跑 agent tool loop。

本模組扮演的角色
----------------
``manager`` 只負責對 MCP Server ``list_tools`` / ``call_tool``；``routing`` + ``providers``
只負責呼叫 LLM。**本模組**把兩者串成迴圈，供 ``core/client.complete(..., mcp_servers=...)`` 使用：

1. 向 ``MCPManager`` 取工具 → 轉成 OpenAI ``tools`` 格式
2. ``invoke_resolved(..., tools=...)`` 問模型
3. 若回傳 ``tool_calls`` → ``run_tool_calls`` 代呼 MCP
4. 將 ``role: tool`` 併回對話 → 重複直到出現最終文字或達 ``max_tool_rounds``

主要入口：``complete_with_mcp_loop``。不處理 yaml／執行期註冊（見 ``registry``、``manager``）；
不實作 HTTP Proxy（見 0.6.1 ``gateway``）。

實作注意：僅支援**非串流**；``MCPError`` 在此層直接拋出；``ProviderError`` 仍可在單輪內走
model fallback。套件總覽見 ``aicentral.mcp``（``mcp/__init__.py``）。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Literal

from aicentral.config import get_config
from aicentral.config.schema import AICentralConfig
from aicentral.core.errors import ProviderError
from aicentral.core.types import Message
from aicentral.mcp.manager import MCPError, MCPManager
from aicentral.routing.router import invoke_resolved, resolve_fallback_chain

McpServersArg = list[str] | Literal["all"] | None
DEFAULT_MAX_TOOL_ROUNDS = 5


def resolve_mcp_server_names(
    mcp_servers: McpServersArg,
    mgr: MCPManager,
) -> list[str]:
    """將 ``mcp_servers``（名稱列表或 ``\"all\"``）解析為實際可用的 server 名稱。"""
    if mcp_servers is None:
        return []
    available = mgr._mcp_servers()  # noqa: SLF001 — 合併 yaml + 執行期註冊
    if mcp_servers == "all":
        names = sorted(available)
    else:
        names = [s.strip() for s in mcp_servers if s.strip()]
    for name in names:
        if name not in available:
            known = ", ".join(sorted(available)) or "無"
            raise MCPError(f"未知 MCP server: {name!r}（已定義: {known}）")
        allowed = mgr._config.mcp_settings.allowed_servers  # noqa: SLF001
        if allowed is not None and name not in allowed:
            raise MCPError(f"MCP server 不在白名單: {name!r}")
    return names


def collect_mcp_openai_tools(
    mgr: MCPManager,
    server_names: list[str],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """向各 server ``list_tools``，並建立 ``工具名 → server 名`` 對照表（供執行 tool_calls 用）。"""
    openai_tools: list[dict[str, Any]] = []
    name_to_server: dict[str, str] = {}
    for server in server_names:
        for tool in mgr.list_tools(server):
            openai_tools.append(mcp_tool_to_openai(tool))
            name_to_server[str(tool["name"])] = str(tool.get("mcp_server", server))
    return openai_tools, name_to_server


def mcp_tool_to_openai(tool: Mapping[str, Any]) -> dict[str, Any]:
    """單一 MCP 工具 → OpenAI Chat Completions 的 ``{type, function}`` 項目。"""
    name = str(tool.get("name", ""))
    description = tool.get("description")
    parameters = tool.get("inputSchema") or {"type": "object", "properties": {}}
    if not isinstance(parameters, dict):
        parameters = {"type": "object", "properties": {}}
    function: dict[str, Any] = {
        "name": name,
        "parameters": parameters,
    }
    if description:
        function["description"] = str(description)
    return {"type": "function", "function": function}


def merge_openai_tools(
    mcp_tools: list[dict[str, Any]],
    user_tools: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """合併 MCP 工具與呼叫方自傳的 ``tools``；同名時 **MCP 覆寫** 使用者定義。"""
    if not user_tools:
        return list(mcp_tools)
    by_name: dict[str, dict[str, Any]] = {}
    for t in user_tools:
        fn = t.get("function") if isinstance(t.get("function"), dict) else t
        if isinstance(fn, dict) and fn.get("name"):
            by_name[str(fn["name"])] = t
    for t in mcp_tools:
        fn = t.get("function", {})
        if isinstance(fn, dict) and fn.get("name"):
            by_name[str(fn["name"])] = t
    return list(by_name.values())


def extract_assistant_message(raw: dict[str, Any]) -> dict[str, Any]:
    """從 provider 回傳的 OpenAI 形狀 JSON 取出 ``choices[0].message``。"""
    choices = raw.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ProviderError(f"無法解析 LLM 回應: {raw!r}")
    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise ProviderError(f"無法解析 LLM 回應 message: {raw!r}")
    return dict(message)


def extract_tool_calls(message: dict[str, Any]) -> list[dict[str, Any]]:
    """助理訊息若含 ``tool_calls`` 則回傳列表，否則空列表（代表可結束 loop）。"""
    tool_calls = message.get("tool_calls")
    if not isinstance(tool_calls, list) or not tool_calls:
        return []
    return [tc for tc in tool_calls if isinstance(tc, dict)]


def run_tool_calls(
    tool_calls: list[dict[str, Any]],
    *,
    mgr: MCPManager,
    name_to_server: dict[str, str],
) -> list[dict[str, Any]]:
    """依模型回傳的 ``tool_calls`` 呼叫 MCP，產生 ``role: tool`` 訊息供下一輪 LLM 使用。"""
    tool_messages: list[dict[str, Any]] = []
    for tc in tool_calls:
        tc_id = tc.get("id")
        if not tc_id:
            raise MCPError(f"tool_call 缺少 id: {tc!r}")
        fn = tc.get("function")
        if not isinstance(fn, dict):
            raise MCPError(f"tool_call 缺少 function: {tc!r}")
        tool_name = str(fn.get("name", ""))
        server = name_to_server.get(tool_name)
        if not server:
            raise MCPError(f"無法對應 MCP server 的工具名稱: {tool_name!r}")
        raw_args = fn.get("arguments", "{}")
        if isinstance(raw_args, str):
            try:
                arguments = json.loads(raw_args) if raw_args.strip() else {}
            except json.JSONDecodeError as exc:
                raise MCPError(f"工具參數非合法 JSON: {raw_args!r}") from exc
        elif isinstance(raw_args, dict):
            arguments = raw_args
        else:
            arguments = {}
        result = mgr.call_tool(server, tool_name, arguments)
        tool_messages.append(
            {
                "role": "tool",
                "tool_call_id": str(tc_id),
                "content": serialize_tool_result(result),
            }
        )
    return tool_messages


def serialize_tool_result(result: Any) -> str:
    """MCP ``call_tool`` 回傳值轉成可放入 message content 的字串。"""
    if result is None:
        return ""
    if isinstance(result, str):
        return result
    try:
        return json.dumps(result, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(result)


def complete_with_mcp_loop(
    messages: list[Message],
    model: str | None,
    *,
    mcp_servers: McpServersArg,
    max_tool_rounds: int = DEFAULT_MAX_TOOL_ROUNDS,
    mcp_manager: MCPManager | None = None,
    config: AICentralConfig | None = None,
    **kwargs: Any,
) -> str:
    """
    帶 MCP 的非串流 complete：自動重複「問模型 → 執行工具 → 再問模型」。

    ``MCPError`` 直接拋出；``ProviderError`` 仍可依 yaml ``router.fallbacks`` 換 model。
    """
    if max_tool_rounds < 1:
        raise ValueError("max_tool_rounds 須 >= 1")

    cfg = config or get_config()
    mgr = mcp_manager or MCPManager.from_config()
    server_names = resolve_mcp_server_names(mcp_servers, mgr)
    if not server_names:
        raise ValueError("mcp_servers 為空，請傳入 server 名稱或 'all'")

    user_tools = kwargs.pop("tools", None)
    if user_tools is not None and not isinstance(user_tools, list):
        raise ValueError("tools 須為 list")

    mcp_openai, name_to_server = collect_mcp_openai_tools(mgr, server_names)
    if not mcp_openai:
        raise MCPError(f"未取得任何 MCP 工具（servers={server_names!r}）")

    tools = merge_openai_tools(mcp_openai, user_tools)
    chain = resolve_fallback_chain(model, config=cfg)
    conversation: list[dict[str, Any]] = [dict(m) for m in messages]
    attempted: list[str] = []
    last_provider_exc: ProviderError | None = None

    for round_idx in range(max_tool_rounds):
        raw: dict[str, Any] | None = None
        for i, resolved in enumerate(chain):
            attempted.append(resolved.model_label)
            try:
                out = invoke_resolved(
                    resolved,
                    conversation,  # type: ignore[arg-type]
                    raw=True,
                    tools=tools,
                    **kwargs,
                )
                assert isinstance(out, dict)
                raw = out
                break
            except ProviderError as exc:
                last_provider_exc = exc
                if exc.is_fallback_eligible(cfg.router.fallback_on) and i < len(chain) - 1:
                    continue
                exc.add_note(f"已嘗試 model: {', '.join(attempted)}")
                raise

        if raw is None:
            assert last_provider_exc is not None
            raise last_provider_exc

        assistant = extract_assistant_message(raw)
        tool_calls = extract_tool_calls(assistant)
        if not tool_calls:
            content = assistant.get("content")
            if content is None:
                raise ProviderError("模型回應無 content 且無 tool_calls")
            return str(content)

        conversation.append(assistant)
        tool_messages = run_tool_calls(
            tool_calls,
            mgr=mgr,
            name_to_server=name_to_server,
        )
        conversation.extend(tool_messages)

        if round_idx == max_tool_rounds - 1:
            raise ProviderError(
                f"MCP tool loop 已達上限（max_tool_rounds={max_tool_rounds}），模型仍要求呼叫工具"
            )

    raise ProviderError("MCP tool loop 未回傳最終文字")
