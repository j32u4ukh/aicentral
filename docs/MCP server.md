# MCP Server（aicentral v4.0）

> 規格：[aicentral-v4.0.md](./aicentral-v4.0.md) · 參考 LiteLLM：`litellm/responses/mcp/`、`litellm/proxy/_experimental/mcp_server/`

---

## MCP 是什麼、放在哪一層

**MCP（Model Context Protocol）** 讓 AI 應用透過統一協定連到外部工具（搜尋、Issue 追蹤、資料庫等）。MCP **不是** LLM：它不產生 chat completion，只提供 `list_tools` / `call_tool`。

| 層級 | 職責 |
|------|------|
| `providers/*` | 呼叫 **LLM**（OpenAI、Anthropic、Gemini、Ollama） |
| `mcp/*` | 連線 **MCP server**、列出與執行工具 |
| `core/client.complete()` | 組裝對話；未來可選編排「模型 ↔ MCP 工具」迴圈 |

LiteLLM 亦將 MCP 放在 **Proxy / Responses** 層，而非 `llms/` 目錄。aicentral 對齊此設計。

---

## 設定方式

在 `config/aicentral.yaml`（或 `AICENTRAL_CONFIG` 指向的檔案）定義 `mcp_servers`：

```yaml
mcp_servers:
  deepwiki:
    transport: http
    url: https://mcp.deepwiki.com/mcp
    description: DeepWiki MCP
    timeout: 30
    auth_type: none

  fetch:
    transport: stdio
    command: uvx
    args: ["mcp-server-fetch"]
    env:
      SOME_VAR: os.environ/SOME_VAR

  linear:
    transport: sse
    url: https://mcp.linear.app/sse
    auth_type: bearer_token
    auth_value: os.environ/LINEAR_API_KEY

mcp_settings:
  tool_name_prefix: true      # 工具名加 server 前綴，避免撞名
  client_timeout: 30
  # allowed_servers: [deepwiki]   # 可選白名單
```

### 欄位說明

| 欄位 | 必填 | 說明 |
|------|------|------|
| `transport` | ✅ | `stdio` \| `http` \| `sse` |
| `url` | http / sse | MCP 端點 URL |
| `command` | stdio | 例如 `uvx`、`npx` |
| `args` | stdio | 命令列參數 |
| `env` | 否 | stdio 子行程環境變數；值可寫 `os.environ/VAR` |
| `auth_type` | 否 | `none`、`bearer_token`、`api_key`、`basic`、`authorization` |
| `auth_value` | 否 | 金鑰或 token |
| `timeout` | 否 | 覆寫 `mcp_settings.client_timeout` |
| `allowed_tools` | 否 | 僅允許列出的工具名 |
| `disallowed_tools` | 否 | 禁用工具名 |
| `static_headers` | 否 | 固定 HTTP header |

---

## Python API

需安裝 MCP 依賴：

```bash
pip install "aicentral[mcp]"
# 或
pip install mcp>=1.6.0
```

### 列出與呼叫工具

```python
from aicentral import MCPManager

mgr = MCPManager.from_config()  # 讀取 aicentral.yaml

tools = mgr.list_tools("deepwiki")
# 若 tool_name_prefix=true，名稱為 deepwiki__<tool_name>

result = mgr.call_tool("deepwiki", "deepwiki__search", {"query": "aicentral"})
```

### 一次列出所有已設定 server

```python
all_tools = mgr.list_all_tools()
```

### 內部 URL 別名（對照 LiteLLM `litellm_proxy/mcp/`）

消費方或日後 Gateway 可用：

```text
aicentral/mcp/<server_name>
```

解析：

```python
from aicentral.mcp import MCPManager

name = MCPManager.parse_server_url("aicentral/mcp/deepwiki")  # -> "deepwiki"
```

v4.0 **library** 不自動在 `complete()` 內執行 MCP tool loop；請在應用層呼叫 `MCPManager`，或待 v4.1 / v5.0 Gateway 整合。

---

## Transport 對照 LiteLLM

| transport | LiteLLM | aicentral 實作 |
|-----------|---------|----------------|
| `stdio` | `MCPClient` + `stdio_client` | `mcp.client.mcp_session` |
| `http` | `streamable_http_client` | 同上（需 mcp 套件支援） |
| `sse` | `sse_client` | 同上 |

連線與 session 生命週期封裝在 `aicentral/mcp/client.py`；多 server 管理在 `aicentral/mcp/manager.py`。

---

## 與 `complete()` 的關係（規劃）

LiteLLM 在 `tools` 參數中接受 `type: "mcp"`，由 `LiteLLM_Proxy_MCP_Handler` 代為 list/call。

aicentral v4.0 已提供 **獨立** `MCPManager`；`complete(..., tools=[...])` 的自動編排列為 **P1 之後**，避免 library 強制綁定特定 agent 迴圈。

建議消費方流程：

1. `tools = mgr.list_tools("my_server")` 轉成模型可用的 function schema（應用層負責）。
2. `complete(messages, tools=functions)` 取得 `tool_calls`。
3. `mgr.call_tool(...)` 執行後，將結果以 `role: tool` 訊息塞回 `messages`，再 `complete`。

---

## 錯誤處理

| 例外 | 時機 |
|------|------|
| `MCPError` | 未知 server、工具不在白名單、設定錯誤 |
| `ImportError` | 未安裝 `mcp` 套件 |

MCP 失敗 **不會** 觸發 LLM router 的 `fallback`（fallback 僅用於 `ProviderError` 連線/逾時）。

---

## v4.0 刻意不做

- MCP OAuth2 / PKCE 全流程（LiteLLM Proxy）
- `mcp_semantic_tool_filter`（依 embedding 篩工具）
- 內建 `mcp_registry.json` 市集一鍵安裝
- HTTP Gateway 對外暴露 `/mcp/*`（見 v5.0）

---

## 範例設定檔

完整範例見 repo 內 [`config/aicentral.yaml`](../config/aicentral.yaml)。
