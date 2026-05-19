# aicentral v0.6.1 — Proxy 暴露 MCP（可選）

> 總覽：[aicentral.md](./aicentral.md) · 前置：**0.6.0**（Library tool loop）· Proxy：[proxy.md](./proxy.md)、[aicentral-v5.0.md](./aicentral-v5.0.md)  
> MCP 執行期註冊（Library）：[mcp.md](./mcp.md) — `register_mcp_server()`

**套件版本**：`0.6.1`（已交付，見 `pyproject.toml`）

---

## 目標

讓**已啟動的本機 Gateway**（`python -m aicentral.gateway`）能透過 HTTP：

1. **MCP Server 列表**：查詢、執行期註冊／更新／移除（對應 Library 的 `register_mcp_server` / `unregister_mcp_server`）。
2. **MCP 工具**：對已登錄的 server 執行 `list_tools` / `call_tool`。

使非 Python 客戶端或 [`aicentral-mcp`](../../aicentral-mcp) 的 HTTP 範例也能管理 MCP 連線並呼叫工具，**無需**在消費方重複實作 MCP Client。

**仍不做的**：對外網開放、OAuth、Gateway 內完整 agent 多輪規劃（多輪 tool loop 建議在 0.6.0 `complete` 完成）、修改磁碟上的 `aicentral.yaml`（HTTP 僅影響**執行期註冊表**）。

---

## 範圍

### 要做

| 項目 | 說明 |
|------|------|
| `gateway/routes/mcp.py` | Server 列表 REST + 工具 REST（見下表） |
| 委派 | Server 列表 → `mcp/registry`；工具 → `MCPManager` |
| 與 yaml 關係 | `GET` 合併顯示 yaml + 執行期註冊；`POST`/`DELETE` 僅改執行期表（不寫回 yaml） |
| 安全 | 沿用 loopback + `LocalClientMiddleware` + 可選 `optional_token` |
| 錯誤 | MCP 失敗 → JSON error body（對齊既有 gateway errors） |
| 測試 | `tests/gateway/test_mcp_routes.py`（TestClient + mock） |
| 文件 | [proxy.md](./proxy.md) 增 MCP 章節 |

### 刻意不做

- Gateway 內自動 `complete` + tool loop（消費方組 `messages` 後仍打 `/v1/chat/completions`）
- MCP OAuth、semantic tool filter、**市集 registry 一鍵匯入**
- 透過 HTTP **編輯** `config/aicentral.yaml` 檔案
- 對 `0.0.0.0` 或公網暴露 MCP 端點

---

## HTTP API 草案

Base：`http://127.0.0.1:{gateway.bind_port}`（見 `config/aicentral.yaml` `gateway:`）

### A. MCP Server 列表（連線註冊）

對應 Library：`register_mcp_server`、`register_mcp_servers`、`unregister_mcp_server`、`registered_mcp_servers`（見 [mcp.md](./mcp.md)）。

| 方法 | 路徑 | 行為 |
|------|------|------|
| `GET` | `/v1/mcp/servers` | 列出**有效** server（yaml ∪ 執行期註冊，含來源標記） |
| `GET` | `/v1/mcp/servers/{server}` | 單一 server 連線設定（**不回傳**明文 `auth_value`，僅 `auth_type` 等） |
| `POST` | `/v1/mcp/servers` | 註冊一個或多個執行期 server（見 body） |
| `PUT` | `/v1/mcp/servers/{server}` | 覆寫執行期註冊的該 server（等同 `register_mcp_server`） |
| `DELETE` | `/v1/mcp/servers/{server}` | 移除**執行期**註冊；若僅存在於 yaml → `409` 或 `404`（實作時擇一並文件化） |

#### `GET /v1/mcp/servers` 回應範例

```json
{
  "servers": [
    {
      "name": "deepwiki",
      "source": "yaml",
      "transport": "http",
      "url": "https://mcp.deepwiki.com/mcp"
    },
    {
      "name": "runtime_fetch",
      "source": "runtime",
      "transport": "stdio",
      "command": "uvx",
      "args": ["mcp-server-fetch"]
    }
  ]
}
```

| 欄位 | 說明 |
|------|------|
| `source` | `yaml` \| `runtime`；同名時以 `runtime` 為準（與 Library 合併規則一致） |
| 敏感欄位 | 列表與 `GET` 單筆皆**不**回傳 `auth_value`；僅 `auth_type: bearer_token` 等 |

#### `POST /v1/mcp/servers` 請求範例

單一：

```json
{
  "name": "my_tools",
  "transport": "http",
  "url": "https://tools.example.com/mcp",
  "auth_type": "bearer_token",
  "auth_value": "secret-token"
}
```

批次：

```json
{
  "servers": {
    "fetch": {
      "transport": "stdio",
      "command": "uvx",
      "args": ["mcp-server-fetch"]
    }
  }
}
```

→ `201`（新建）或 `200`（覆寫）；body 與 `MCPServerEntry` 欄位一致（見 [mcp.md](./mcp.md) 欄位表）。

#### `DELETE /v1/mcp/servers/{server}`

- 僅刪除執行期註冊；yaml 內定義的 server 仍存在於合併列表，直到重啟或改 yaml。
- 回應：`204` 或 `200` + `{"removed": true}`。

---

### B. MCP 工具（對已登錄 server）

| 方法 | 路徑 | 行為 |
|------|------|------|
| `GET` | `/v1/mcp/{server}/tools` | 轉發 `MCPManager.list_tools(server)` |
| `POST` | `/v1/mcp/{server}/tools/{tool_name}` | Body: `{"arguments": {...}}` → `call_tool` |

`{server}` 須出現在合併後的有效列表中（yaml 或執行期）；否則 `404`。

#### 回應範例

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
        ├─ /v1/mcp/servers*  → mcp/registry（執行期列表）
        │
        └─ /v1/mcp/{server}/tools*  → MCPManager → mcp/client → 外部 MCP Server
```

**流程範例（外部專案僅 HTTP、不 import）**：

1. `POST /v1/mcp/servers` 註冊執行期 server（或依賴 yaml 已有項目）。
2. `GET /v1/mcp/servers` 確認列表。
3. `GET /v1/mcp/{server}/tools` 取得工具 schema。
4. `POST /v1/chat/completions`（可選，若模型支援 tools）。
5. `POST /v1/mcp/{server}/tools/{tool}` 執行工具。
6. 再 `POST /v1/chat/completions` 帶 tool 結果（編排在消費方）。

Chat Completions 與 MCP 路由**分離**；單一 HTTP 請求內跑完 tool loop 不在 0.6.1 範圍。

---

## 實作任務清單

| # | 任務 | 產出 |
|---|------|------|
| 1 | Server 列表路由 | `GET/POST/PUT/DELETE /v1/mcp/servers` |
| 2 | 工具路由 | `GET/POST .../tools` |
| 3 | `gateway/schemas.py` | `MCPServerRegisterBody`、列表回應（遮罩 secret） |
| 4 | `gateway/app.py` 掛載 | `include_router` |
| 5 | 與 `registry` 整合 | HTTP `POST` → `register_mcp_server`；`DELETE` → `unregister_mcp_server` |
| 6 | 依賴 | `pip install "aicentral[gateway,mcp]"` 文件化 |
| 7 | `tests/gateway/test_mcp_routes.py` | 列表 CRUD + tools mock |
| 8 | [proxy.md](./proxy.md) | curl：註冊 server → list tools → call tool |
| 9 | 安全複測 | 非 loopback → 403；回應不含 `auth_value` |

---

## 消費方範例規劃

### curl — Server 列表 + 工具

```powershell
# 終端 1：Proxy
python -m aicentral.gateway

# 終端 2 — 列表
curl -s http://127.0.0.1:8080/v1/mcp/servers

# 執行期註冊（無需改 yaml）
curl -s -X POST http://127.0.0.1:8080/v1/mcp/servers ^
  -H "Content-Type: application/json" ^
  -d "{\"name\":\"fetch\",\"transport\":\"stdio\",\"command\":\"uvx\",\"args\":[\"mcp-server-fetch\"]}"

curl -s http://127.0.0.1:8080/v1/mcp/servers/fetch

# 工具
curl -s http://127.0.0.1:8080/v1/mcp/deepwiki/tools
curl -s -X POST http://127.0.0.1:8080/v1/mcp/deepwiki/tools/deepwiki__search ^
  -H "Content-Type: application/json" ^
  -d "{\"arguments\": {\"query\": \"Model Context Protocol\"}}"

# 移除執行期註冊
curl -s -X DELETE http://127.0.0.1:8080/v1/mcp/servers/fetch
```

### [`aicentral-mcp`](../../aicentral-mcp) HTTP 範例

可重用函式見 `mcp_http_common.py`：`list_mcp_servers`、`register_mcp_server_http`、`list_mcp_tools`、`call_mcp_tool` 等。

| 腳本 | 說明 |
|------|------|
| `example_http_01_servers.py` | `/v1/mcp/servers` |
| `example_http_02_tools.py` | `list_tools` / `call_tool` |
| `example_http_03_overview.py` | 列表 + 工具一覽 |

### Import 與 HTTP 的選擇（均在 aicentral-mcp）

| 腳本 | 路徑 | 適用 |
|------|------|------|
| `example_02` / `example_03` | `Chat.with_mcp` + `ask()` | Python、自動 tool loop |
| `example_http_*` | Proxy `/v1/mcp/*` | HTTP 客戶端、分步呼叫工具 |

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

**路徑 B — HTTP 分步（0.6.1）**

1. `GET /v1/mcp/servers`（必要時 `POST` 註冊執行期 server）
2. `GET /v1/mcp/deepwiki/tools`
3. `POST /v1/chat/completions` + `tools`
4. `POST /v1/mcp/deepwiki/tools/{name}` 執行 tool
5. 再 `POST /v1/chat/completions` 帶 `role: tool` 訊息

路徑 B 的編排可由 `aicentral-mcp` 的 HTTP 範例或外部腳本實作；Gateway **只提供積木**。

---

## 驗收標準

### Server 列表

- [x] 僅 `127.0.0.1` 可存取；他機 403（沿用 gateway localhost 中介層）
- [x] `GET /v1/mcp/servers` 回傳 yaml + 執行期合併列表，含 `source`
- [x] `POST /v1/mcp/servers` 註冊後，`GET` 可見且 `MCPManager` 可 `list_tools`
- [x] `DELETE /v1/mcp/servers/{name}` 僅移除執行期項；yaml-only 回 404
- [x] 回應 JSON **永不**包含 `auth_value`（僅接受於 `POST`/`PUT` body）

### 工具

- [x] `GET /v1/mcp/{server}/tools` 在 mock 或整合環境回傳工具列表
- [x] `POST .../tools/{tool}` 在 mock 環境回傳 200

### 其他

- [x] 未安裝 `mcp` 套件時 MCP 路由回 503
- [x] [proxy.md](./proxy.md) 含 Server 列表與工具 curl 範例
- [x] [`aicentral-mcp`](../../aicentral-mcp) HTTP 範例（`mcp_http_common`、`example_http_*`）

---

## 與其他文件

| 文件 | 關係 |
|------|------|
| [aicentral-v0.6.0.md](./aicentral-v0.6.0.md) | Library tool loop（建議先做） |
| [mcp.md](./mcp.md) | `MCPServerEntry` 欄位、`register_mcp_server()` |
| [aicentral-v5.0.md](./aicentral-v5.0.md) | Proxy 安全與 chat 端點 |
