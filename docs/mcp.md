# MCP（Client 連線外部 Server）

> 架構：[aicentral.md](./aicentral.md) · 規格：[aicentral-v4.0.md](./aicentral-v4.0.md) · 參考 LiteLLM：`litellm/responses/mcp/`

---

## MCP 是什麼、放在哪一層

**MCP（Model Context Protocol）** 讓 AI 應用透過統一協定連到外部工具（搜尋、Issue 追蹤、資料庫等）。MCP **不是** LLM：它不產生 chat completion，只提供 `list_tools` / `call_tool`。

| 層級 | 職責 |
|------|------|
| `providers/*` | 呼叫 **LLM**（OpenAI、Anthropic、Gemini、Ollama） |
| `mcp/*` | 連線 **MCP server**、列出與執行工具 |
| `core/client.complete()` | 組裝對話；**0.6.0** 起可選 `mcp_servers` 自動編排 tool loop |

LiteLLM 亦將 MCP 放在 **Proxy / Responses** 層，而非 `llms/` 目錄。aicentral 對齊此設計。

---

## 設定方式

### YAML（預設）

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

### 執行期註冊（外部專案）

不需修改 aicentral repo 的 yaml 時，可在應用啟動時註冊：

```python
from aicentral import MCPManager, register_mcp_server, register_mcp_servers, MCPServerEntry

# 單一 server（關鍵字參數同 MCPServerEntry 欄位）
register_mcp_server(
    "my_tools",
    transport="http",
    url="https://tools.example.com/mcp",
    auth_type="bearer_token",
    auth_value="your-token",
)

# 或批次
register_mcp_servers({
    "fetch": {
        "transport": "stdio",
        "command": "uvx",
        "args": ["mcp-server-fetch"],
    },
})

mgr = MCPManager.from_config()  # yaml + 註冊表合併
tools = mgr.list_tools("my_tools")
```

| 函式 | 說明 |
|------|------|
| `register_mcp_server(name, ...)` | 註冊一個 server；同名會覆寫 yaml |
| `register_mcp_servers(dict)` | 批次註冊 |
| `unregister_mcp_server(name)` | 移除執行期註冊 |
| `registered_mcp_servers()` | 查看目前註冊表 |
| `MCPManager(cfg, extra_servers={...})` | 僅該實例額外 server，不寫入全域註冊表 |

合併順序：**yaml** → **全域註冊** → **`extra_servers`**（後者優先）。

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

未傳 `mcp_servers` 時，`complete()` 行為與純 LLM 相同；可改用手動 `MCPManager` 或 **`complete(..., mcp_servers=[...])`**。Proxy HTTP 見 **0.6.1**（可選）。

---

## 消費方範例（aicentral-mcp）

獨立示範專案 [`aicentral-mcp`](../../aicentral-mcp) 提供可 import 的範例函式與腳本：

| 腳本 | 對應 API |
|------|----------|
| `example_01_manager_manual.py` | `MCPManager.list_tools` / `call_tool`、`mcp_tool_to_openai` |
| `example_02_complete_mcp.py` | `complete(..., mcp_servers=...)` |
| `example_03_chat_mcp.py` | `Chat(mcp_servers=...)` |
| `example_04_register_server.py` | `register_mcp_server` + 合併設定 |

```powershell
cd aicentral-mcp
pip install -e .
python example_02_complete_mcp.py
```

對話 + MCP 的簡化 REPL 亦可見 [`aicentral-chat/chat_mcp.py`](../../aicentral-chat/chat_mcp.py)。

---

## Transport 對照 LiteLLM

| transport | LiteLLM | aicentral 實作 |
|-----------|---------|----------------|
| `stdio` | `MCPClient` + `stdio_client` | `mcp.client.mcp_session` |
| `http` | `streamable_http_client` | 同上（需 mcp 套件支援） |
| `sse` | `sse_client` | 同上 |

連線與 session 生命週期封裝在 `aicentral/mcp/client.py`；多 server 管理在 `aicentral/mcp/manager.py`。

---

## 與 `complete()` 的關係

LiteLLM 在 `tools` 參數中接受 `type: "mcp"`，由 Proxy 代為 list/call。

**0.6.0** 起可自動執行 tool loop（**非串流**）；呼叫方只需提問，不必組 `messages` / `tools`：

```python
from aicentral import Chat, complete, ask_mcp

# 單次
reply = complete("用 DeepWiki 查 aicentral", mcp_servers=["deepwiki"])

# 或多輪（推薦）
chat = Chat.with_mcp(["deepwiki"])
reply = chat.ask("MCP 協定是什麼？")
reply2 = chat.ask("再簡述上一題重點")
```

仍可直接使用 `MCPManager` 手動編排；Proxy HTTP 見 **[aicentral-v0.6.1.md](./aicentral-v0.6.1.md)**（規劃中）。

---

## 錯誤處理

| 例外 | 時機 |
|------|------|
| `MCPError` | 未知 server、工具不在白名單、設定錯誤 |
| `ImportError` | 未安裝 `mcp` 套件 |

MCP 失敗 **不會** 觸發 LLM router 的 `fallback`（fallback 僅用於 `ProviderError` 連線/逾時）。

---

## 認證（0.5.0 已支援）

| `auth_type` | 用途 |
|-------------|------|
| `none` | 無需 token（如 DeepWiki） |
| `bearer_token` / `api_key` / `basic` | 靜態金鑰，可寫 `secret/mcp.<server>.auth_value` |

不需 OAuth 模組即可接多數 MCP；OAuth2 / PKCE 全流程**不在計畫內**（見下方）。

## 不在範圍內（保持輕量，非延後）

以下能力**不預排版本**；需求明確時再議是否加入 aicentral 或由消費方實作：

- MCP OAuth2 / PKCE 全流程
- `mcp_semantic_tool_filter`、內建 registry 市集一鍵匯入
- MCP 專用 metrics／可觀測平台
- Gateway 對外網開放 `/mcp/*`（本機 Proxy 僅 loopback；**0.6.1** 可選本機轉發）

---

## 範例設定檔

完整範例見 repo 內 [`config/aicentral.yaml`](../config/aicentral.yaml)。
