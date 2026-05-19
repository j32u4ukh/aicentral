"""aicentral MCP 工具層（v0.6.0）。

本套件扮演的角色
----------------
aicentral 透過 **MCP（Model Context Protocol）** 連到外部工具服務（搜尋、Issue、檔案等）。
MCP **不是** LLM：不產生 chat completion，只提供 ``list_tools`` / ``call_tool``。
因此 MCP 放在獨立 ``mcp/`` 套件，**不**註冊為 ``providers/*`` 的一種 model。

與 Cursor SKILL 的分工
~~~~~~~~~~~~~~~~~~~~~~
- **MCP 工具**：各 server 經協定回傳 ``name``、``description``、``inputSchema``，模型依此決定
  何時呼叫——**不必**在 aicentral 另寫 SKILL 類用法文件。
- **aicentral**：只做 **MCP Client**（連線、列工具、代呼工具）與可選的 **tool loop 編排**。

子模組
~~~~~~
| 模組 | 職責 |
|------|------|
| ``client`` | stdio / http / sse 連線（官方 ``mcp`` 套件） |
| ``manager`` | 多 server 管理、``list_tools`` / ``call_tool`` |
| ``registry`` | 執行期 ``register_mcp_server()``，與 yaml 合併 |
| ``orchestrator`` | ``complete(..., mcp_servers=...)`` 的 agent tool loop |

對外入口（呼叫方只需提問，不必組 LLM messages）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- **推薦**：``Chat.with_mcp(["deepwiki"]).ask("你的問題")`` — 有狀態多輪、自動 tool loop
- 單次：``complete("你的問題", mcp_servers=["deepwiki"])`` — 字串即 user 訊息
- 手動工具：``MCPManager.from_config()`` → ``list_tools`` / ``call_tool``
- 進階：``complete_with_mcp_loop``（訊息列表、自訂迴圈）
- 設定：``config/aicentral.yaml`` 的 ``mcp_servers``；亦可 ``register_mcp_server()``
- HTTP 暴露 MCP：見 **0.6.1** Gateway（``gateway/routes/mcp``，規劃／文件中）

錯誤分工
~~~~~~~~
- ``MCPError``：未知 server、工具白名單、連線／協定失敗；**不**觸發 LLM ``router`` fallback
- ``ProviderError``：LLM 端點失敗；可依 yaml ``router.fallbacks`` 換 model

依賴：``pip install "aicentral[mcp]"``（``mcp>=1.6.0``）。
"""

from aicentral.config.schema import MCPServerEntry
from aicentral.mcp.manager import AICENTRAL_MCP_PREFIX, MCPError, MCPManager
from aicentral.mcp.orchestrator import (
    ask_mcp,
    complete_with_mcp_loop,
    mcp_tool_to_openai,
    resolve_mcp_server_names,
)
from aicentral.mcp.registry import (
    clear_mcp_registry,
    register_mcp_server,
    register_mcp_servers,
    registered_mcp_servers,
    unregister_mcp_server,
)

__all__ = [
    "AICENTRAL_MCP_PREFIX",
    "MCPServerEntry",
    "MCPError",
    "MCPManager",
    "ask_mcp",
    "complete_with_mcp_loop",
    "mcp_tool_to_openai",
    "resolve_mcp_server_names",
    "clear_mcp_registry",
    "register_mcp_server",
    "register_mcp_servers",
    "registered_mcp_servers",
    "unregister_mcp_server",
]
