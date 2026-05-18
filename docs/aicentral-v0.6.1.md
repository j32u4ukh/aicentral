# aicentral v0.6.1 — Proxy 暴露 MCP（可選）

> 總覽：[aicentral.md](./aicentral.md) · 前置：**0.6.0**（Library tool loop）· Proxy：[proxy.md](./proxy.md)、[aicentral-v5.0.md](./aicentral-v5.0.md)

**套件版本**：`0.6.1`（可選里程碑；若僅需 Python `import`，可略過本版）

---

## 目標

讓**已啟動的本機 Gateway**（`python -m aicentral.gateway`）能透過 HTTP **轉發** `MCPManager` 的 `list_tools` / `call_tool`，使非 Python 客戶端或 `aicentral-chat` 的 HTTP 路徑也能觸發 MCP，**無需**在消費方重複實作 MCP Client。

**仍不做的**：對外網開放、OAuth、Gateway 內完整 agent 多輪規劃（多輪 tool loop 建議在消費方或 0.6.0 `complete` 完成）。

---

## 範圍

### 要做

| 項目 | 說明 |
|------|------|
| `gateway/routes/mcp.py` | REST 路由（見下表） |
| 委派 | 僅呼叫 `MCPManager`，不直連 MCP 協定 |
| 安全 | 沿用 loopback + `LocalClientMiddleware` + 可選 `optional_token` |
| 錯誤 | MCP 失敗 → JSON error body（對齊既有 gateway errors） |
| 測試 | `tests/gateway/test_mcp_routes.py`（TestClient + mock manager） |
| 文件 | [proxy.md](./proxy.md) 增 MCP 章節 |

### 刻意不做

- Gateway 內自動 `complete` + tool loop（消費方組 `messages` 後仍打 `/v1/chat/completions`）
- MCP OAuth、semantic filter、registry
- 對 `0.0.0.0` 或公網暴露 MCP 端點

---

## HTTP API 草案

Base：`http://127.0.0.1:{gateway.bind_port}`（見 `config/aicentral.yaml` `gateway:`）

| 方法 | 路徑 | 行為 |
|------|------|------|
| `GET` | `/v1/mcp/servers` | 回傳已設定且通過白名單的 server 名稱列表 |
| `GET` | `/v1/mcp/{server}/tools` | 轉發 `MCPManager.list_tools(server)` |
| `POST` | `/v1/mcp/{server}/tools/{tool_name}` | Body: `{"arguments": {...}}` → `call_tool` |

### 回應範例

`GET /v1/mcp/servers`：

```json
{"servers": ["deepwiki"]}
```

`GET /v1/mcp/deepwiki/tools`：

```json
{
  "tools": [
    {
      "name": "deepwiki__search",
      "description": "...",
      "inputSchema": {"type": "object", "properties": {...}},
      "mcp_server": "deepwiki"
    }
  ]
}
```

`POST /v1/mcp/deepwiki/tools/deepwiki__search`：

```json
{"arguments": {"query": "aicentral MCP"}}
```

→ `200` + tool 結果（結構依 MCP server；gateway 以 JSON 包裝 content）。

---

## 架構

```
curl / aicentral-chat (HTTP)
        │
        ▼
  gateway/routes/mcp.py   ← loopback only
        │
        ▼
  MCPManager.from_config()
        │
        ▼
  mcp/client.py → 外部 MCP Server
```

Chat Completions（`/v1/chat/completions`）與 MCP 路由**分離**；消費方可：

1. `GET .../tools` 取得 schema；
2. `POST .../chat/completions` 帶 `tools`（若模型支援）；
3. `POST .../mcp/.../tools/...` 執行 tool；
4. 再 `POST .../chat/completions` 帶 tool 結果。

未來若要在單一 HTTP 請求內跑完 loop，屬消費方或更高層 BFF，不在 0.6.1 範圍。

---

## 實作任務清單

| # | 任務 | 產出 |
|---|------|------|
| 1 | `gateway/routes/mcp.py` | 三個端點 + 錯誤處理 |
| 2 | `gateway/app.py` 掛載路由 | `include_router` |
| 3 | `gateway/schemas.py`（可選） | Pydantic 請求/回應型別 |
| 4 | 依賴 | `pip install "aicentral[gateway,mcp]"` 文件化 |
| 5 | `tests/gateway/test_mcp_routes.py` | mock `MCPManager` |
| 6 | [proxy.md](./proxy.md) | curl 範例、與 chat 分工 |
| 7 | 安全複測 | 非 loopback client → 403 |

---

## 消費方範例規劃

### curl（驗收用）

```powershell
# 終端 1：Proxy
python -m aicentral.gateway

# 終端 2
curl -s http://127.0.0.1:8080/v1/mcp/servers
curl -s http://127.0.0.1:8080/v1/mcp/deepwiki/tools
curl -s -X POST http://127.0.0.1:8080/v1/mcp/deepwiki/tools/deepwiki__search ^
  -H "Content-Type: application/json" ^
  -d "{\"arguments\": {\"query\": \"Model Context Protocol\"}}"
```

### `aicentral-chat/chat_mcp_http.py`（規劃）

```python
#!/usr/bin/env python3
"""經本機 Proxy HTTP 列出 MCP 工具並執行（示範 0.6.1）。"""

import httpx

from chat_common import require_aicentral_config, resolved_model
from chat_http import gateway_base_url, gateway_api_key


def list_mcp_tools(server: str) -> list[dict]:
    base = gateway_base_url()
    headers = {}
    if token := gateway_api_key():
        headers["Authorization"] = f"Bearer {token}"
    r = httpx.get(f"{base}/v1/mcp/{server}/tools", headers=headers, timeout=30.0)
    r.raise_for_status()
    return r.json()["tools"]


def call_mcp_tool(server: str, tool_name: str, arguments: dict) -> object:
    base = gateway_base_url()
    # POST .../v1/mcp/{server}/tools/{tool_name}
    ...


def main() -> None:
    require_aicentral_config()
    tools = list_mcp_tools("deepwiki")
    print(f"可用工具: {[t['name'] for t in tools]}")
    # 進階：與 OpenAI SDK 或手動 POST /v1/chat/completions 組合成完整對話
```

### 與 0.6.0 `chat_mcp.py` 的選擇

| 腳本 | 路徑 | 適用 |
|------|------|------|
| `chat_mcp.py` | `import Chat` + `mcp_servers=` | 純 Python、單進程 |
| `chat_mcp_http.py` | Proxy `/v1/mcp/*` + `/v1/chat/completions` | 驗證 HTTP、或非 Python 客戶端參考 |

---

## 完整對話範例（跨 0.6.0 + 0.6.1，規劃）

**場景**：使用者問「用 DeepWiki 查 aicentral 架構重點」。

**路徑 A — 僅 Library（0.6.0）**

```python
from aicentral import complete

print(complete(
    [{"role": "user", "content": "用 DeepWiki 查 aicentral 架構重點"}],
    mcp_servers=["deepwiki"],
    max_tool_rounds=5,
))
```

**路徑 B — HTTP 分步（0.6.1 + 既有 chat）**

1. `GET /v1/mcp/deepwiki/tools`
2. `POST /v1/chat/completions` + `tools`（body 含 messages）
3. 若回應含 `tool_calls` → `POST /v1/mcp/deepwiki/tools/{name}`
4. 再 `POST /v1/chat/completions` 帶 `role: tool` 訊息

路徑 B 的編排可由 `chat_mcp_http.py` 或外部腳本實作；Gateway **只提供積木**。

---

## 驗收標準

- [ ] 僅 `127.0.0.1` 可存取 MCP 路由；他機 403
- [ ] `GET /v1/mcp/servers` 回傳 yaml 內 server 名稱
- [ ] `GET /v1/mcp/{server}/tools` 在 mock 或整合環境回傳工具列表
- [ ] `POST .../tools/{tool}` 在 mock 環境回傳 200
- [ ] 未安裝 `[mcp]` 時啟動 Gateway 行為明確（略過路由或啟動時提示）
- [ ] [proxy.md](./proxy.md) 含 MCP curl 與與 chat 端點分工說明

---

## 與其他文件

| 文件 | 關係 |
|------|------|
| [aicentral-v0.6.0.md](./aicentral-v0.6.0.md) | Library tool loop（建議先做） |
| [aicentral-v5.0.md](./aicentral-v5.0.md) | Proxy 安全與 chat 端點；v5.1 MCP HTTP 構想併入本版 |
| [mcp.md](./mcp.md) | MCP Client 設定 |
