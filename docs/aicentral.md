# aicentral 專案架構

> 參考：[litellm.md](./litellm.md)、[instructor.md](./instructor.md)  
> 概念說明（`complete()` 用途等）：[concepts.md](./concepts.md)  
> Proxy 使用：[proxy.md](./proxy.md) · MCP 使用：[mcp.md](./mcp.md)  
> 定位：輕量化合併 LiteLLM（統一呼叫）與 Instructor（結構化輸出）的設計思想，**不依賴** `litellm` / `instructor` 套件。

**套件版本**以 [`pyproject.toml`](../pyproject.toml) 的 `version` 為準（目前 **0.5.0**）。下文「0.x」指套件 semver，與早期文件中的「v1.0～v5.0 里程碑」不同；歷史里程碑說明見文末連結。

---

## 專案定位

**aicentral 是提供給其他專案使用的 AI 能力函式庫（library）**，不是承載業務的應用服務：

- ✅ 對外提供 `complete()`、`complete_structured()`、`Chat` 等，由消費方 `import` 使用
- ✅ 可選 **HTTP Proxy**（`pip install "aicentral[gateway]"`、`python -m aicentral.gateway`）
- ✅ 可選 **MCP 工具層**（`pip install "aicentral[mcp]"`、`MCPManager`）
- ❌ 不在此 repo 封裝業務 API、領域 model、workflow
- ❌ 業務邏輯放在**消費方專案**（例如 [`aicentral-chat`](../../aicentral-chat)）

```
aicentral-chat / 你的後端
        │
        ├─ import：complete / Chat / complete_structured
        ├─ HTTP：POST /v1/chat/completions（本機 Proxy）
        └─ MCP：MCPManager.list_tools / call_tool
        ▼
   aicentral（能力層）
        │
        ├─ routing → providers（Ollama / OpenAI / Anthropic / Gemini）
        └─ mcp/（外部工具，非 LLM）
```

---

## 0.5.0 已交付能力

| 領域 | 模組 / API | 說明 |
|------|------------|------|
| 對話 | `complete()`、`Chat` | 統一 messages、串流、繁中語系等 |
| 結構化 | `complete_structured()`、`structured/*` | Pydantic 驗證與重試 |
| 路由 | `routing/parser`、`routing/router` | `provider/model`、yaml `model_list`、fallback |
| 設定 | `config/loader`、`config/schema` | `config/aicentral.yaml` + `config/secret.yaml` |
| 供應商 | `providers/*` | Ollama（OpenAI 相容）、OpenAI、Anthropic、Gemini |
| MCP（基礎） | `mcp/client`、`mcp/manager`、`mcp/registry` | yaml 或 `register_mcp_server()`；`list_tools` / `call_tool` |
| Proxy | `gateway/*` | 本機 loopback、`POST /v1/chat/completions`、SSE |

驗收（開發機）：

```powershell
cd aicentral
pip install -e ".[dev,gateway,mcp]"
pytest

# 直接 import
python -c "from aicentral import complete; print(complete([{'role':'user','content':'hi'}]))"

# 本機 Proxy（另一終端）
python -m aicentral.gateway

# 消費方範例
cd ..\aicentral-chat
python chat.py          # import Chat
python chat_http.py     # HTTP Proxy
```

---

## 目錄結構（0.5.0）

```
src/aicentral/
├── __init__.py          # complete、Chat、MCPManager、設定載入
├── client.py / chat.py  # 高階 API
├── core/                # complete、型別、錯誤
├── providers/           # LLM 適配與 registry
├── routing/             # parse_model、router、fallback
├── structured/          # schema、extract、validate、retry
├── config/              # yaml 載入、secret 展開
├── mcp/                 # MCP client + manager（非 provider）
└── gateway/             # 可選 FastAPI Proxy

config/
├── aicentral.yaml       # defaults、model_list、router、mcp_servers、gateway
└── secret.yaml          # 機密（勿提交；見 secret.yaml.example）

tests/                   # core、providers、routing、structured、mcp、gateway
```

**依賴方向**：`gateway` → `core` → `providers` / `routing` / `structured`；`mcp` 可獨立使用，**禁止** `providers` 依賴 `structured` 或反向耦合 MCP 與 LLM fallback。

**協定分層**：`core` 使用與供應商無關的 `messages` 語意；`providers/` 轉成各後端 HTTP；`gateway/` 對外提供 OpenAI 相容 REST，內部委派 `core.complete()`；`mcp/` 只處理工具協定，不產生 chat completion。

---

## 設定與消費方

| 檔案 | 用途 |
|------|------|
| `config/aicentral.yaml` | 主設定：`defaults`、`model_list`、`router`、`mcp_servers`、`gateway` |
| `config/secret.yaml` | 巢狀機密；`secret/ollama.api_key` 等形式由 loader 展開 |
| `register_mcp_server()` | 執行期註冊 MCP server，與 yaml 合併（見 [mcp.md](./mcp.md)） |

[`aicentral-chat`](../../aicentral-chat) 為獨立示範專案：`chat.py`（直接 `Chat`）、`chat_http.py`（本機 Proxy）。**禁止**在消費方直接 `httpx` 打 Ollama 或繞過 aicentral 的路由／設定。

---

## 與上游概念的對照

| 上游 | aicentral 模組 | 0.5.0 狀態 |
|------|----------------|------------|
| LiteLLM `completion()` | `complete()` | ✅ |
| LiteLLM `llms/*` | `providers/*` | ✅ |
| LiteLLM `router_strategy/*` | `routing/*` | ✅ |
| Instructor `response_model` | `complete_structured()` + `structured/*` | ✅ |
| LiteLLM `proxy/*` | `gateway/*`（本機） | ✅ |
| LiteLLM `responses/mcp/` | `mcp/*` | ⚠️ 基礎 client；編排見下方 0.6+ |
| 業務 / 對話 UI | **消費方**（`aicentral-chat` 等） | ✅ |

---

## 後續規劃：MCP 與工具編排（0.6.x）

0.5.0 已能透過 **`MCPManager`** 手動 `list_tools` / `call_tool`，但 **`complete()` / `Chat` / Proxy 尚未內建「模型 ↔ MCP 工具」自動迴圈**。目前路線圖**僅保留 MCP MVP**，其餘進階能力**不預排版本**——需求變複雜時再在消費方或 aicentral 按需擴充。

| 版本 | 目標 | 主要產出 | 驗收 |
|------|------|----------|------|
| **0.6.0** | Library 工具編排 | `core` 辨識 OpenAI 風格 `tools` 中的 MCP 宣告；委派 `MCPManager` 執行 `call_tool`；`Chat` 可選開啟 tool loop | `complete(..., mcp_servers=[...])` 跑通一輪 list → call → 再 complete · 規格：[aicentral-v0.6.0.md](./aicentral-v0.6.0.md) |
| **0.6.1**（可選） | Proxy 暴露 MCP | `gateway`：MCP server 列表 CRUD（執行期註冊）+ `list_tools` / `call_tool`；仍僅 loopback | curl 管理 server 列表並呼叫工具 · 規格：[aicentral-v0.6.1.md](./aicentral-v0.6.1.md) |

**0.5.0 已足夠的認證**：`auth_type: none` / `bearer_token` / `basic` + `secret.yaml` 靜態 token，無需另做 OAuth 模組即可接多數遠端 MCP。

### 刻意不做（非延後，保持輕量）

以下**不在路線圖**；若日後确有需求再單独立項，避免預先膨脹函式庫：

| 項目 | 說明 |
|------|------|
| MCP OAuth2 / PKCE 全流程 | 靜態 bearer 已可接多數服務；OAuth 由消費方或 IDE 處理 |
| `mcp_semantic_tool_filter`、registry 市集一鍵匯入 | LiteLLM 進階能力；非 MVP |
| MCP 專用可觀測／metrics 平台 | 先用應用層日誌；有需要再加 |
| Gateway 對外網開放 MCP | 與本機 Proxy 定位不符 |

### 0.6.0 — `complete()` 與 MCP 編排（規劃）

> 完整任務、API 草案、驗收與 `aicentral-chat/chat_mcp.py` 範例見 **[aicentral-v0.6.0.md](./aicentral-v0.6.0.md)**。

**原則**：MCP 仍**不**註冊為 `providers/mcp`；編排邏輯放在 `core/`（或薄層 `mcp/orchestrator.py`），由 `complete()` / `Chat` 在偵測到 MCP 工具時呼叫 `MCPManager`。

```
complete(messages, tools=[...])
  → 分離一般 function tools 與 MCP 工具（server_name / aicentral/mcp/<name>）
  → MCPManager.list_tools / call_tool
  → 將 tool result 併回 messages
  → 再走既有 routing → providers（不觸發 LLM fallback）
```

| 項目 | 說明 |
|------|------|
| 設定 | 沿用 `mcp_servers`、`mcp_settings`；機密 `secret/mcp.*` |
| 依賴 | `pip install "aicentral[mcp]"`（`mcp>=1.6.0`） |
| 錯誤 | `MCPError` 不觸發 router 的 provider fallback |
| 認證 | 沿用 0.5.0 的 bearer / basic + `secret/mcp.*`；不實作 OAuth |

### 0.6.1 — Proxy 與 MCP HTTP（可選）

> 完整 HTTP 契約、curl／`chat_mcp_http.py` 範例見 **[aicentral-v0.6.1.md](./aicentral-v0.6.1.md)**。

對照 LiteLLM Proxy 的 MCP 掛載，在**本機** Gateway 增加 REST（路徑草案，實作時以程式為準）：

**Server 列表**（對應 `register_mcp_server` / `unregister_mcp_server`）：

| 方法 | 路徑（草案） | 行為 |
|------|--------------|------|
| `GET` | `/v1/mcp/servers` | 合併列出 yaml + 執行期 server |
| `POST` | `/v1/mcp/servers` | 執行期註冊（單一或批次） |
| `PUT` | `/v1/mcp/servers/{server}` | 覆寫執行期註冊 |
| `DELETE` | `/v1/mcp/servers/{server}` | 移除執行期註冊 |

**工具**：

| 方法 | 路徑（草案） | 行為 |
|------|--------------|------|
| `GET` | `/v1/mcp/{server}/tools` | 轉發 `list_tools` |
| `POST` | `/v1/mcp/{server}/tools/{tool}` | 轉發 `call_tool` |

仍遵守 v5.0 Proxy 約束：僅 `127.0.0.1`、可選 `optional_token`、**不**在 Gateway 內實作完整 agent workflow（多輪規劃留給消費方）。

### 消費方範例（規劃後）

| 專案 | 0.5.0 | 0.6+ |
|------|-------|------|
| `aicentral-chat` | `chat.py`、`chat_http.py` | 可選 `chat_mcp.py`：示範 tool loop 或 HTTP MCP |

詳細欄位與 LiteLLM 對照見 [mcp.md](./mcp.md)、[aicentral-v4.0.md](./aicentral-v4.0.md)（MCP 分層）、[aicentral-v5.0.md](./aicentral-v5.0.md)（Proxy 規格）。

---

## 歷史里程碑文件（已完成，供對照）

早期路線圖以「v1.0～v5.0」描述漸進交付；對應能力已併入 **0.5.0**。細節請查各版紀錄，**勿**再當作待辦清單：

| 文件 | 對應能力 |
|------|----------|
| [aicentral-v1.0.md](./aicentral-v1.0.md) | `complete()` + Ollama |
| [aicentral-v2.0.md](./aicentral-v2.0.md) | `core/`、`routing/` |
| [aicentral-v3.0.md](./aicentral-v3.0.md) | `structured/` |
| [aicentral-v4.0.md](./aicentral-v4.0.md) | 多 provider、yaml、`mcp/` 基礎 |
| [aicentral-v5.0.md](./aicentral-v5.0.md) | `gateway/` 本機 Proxy |

---

## 小結

| 問題 | 答案 |
|------|------|
| 目前版本？ | **0.5.0**（見 `pyproject.toml`） |
| 現在能做什麼？ | 多供應商對話、結構化輸出、yaml 設定、MCP 手動呼叫、本機 HTTP Proxy |
| 下一步做什麼？ | **0.6.0** MCP 工具編排；**0.6.1** 可選 Proxy MCP HTTP |
| 業務放哪？ | **消費方專案**，不在 aicentral |
| MCP 是 LLM 嗎？ | **否**；獨立 `mcp/` 模組，不經 `parse_model` 選 provider |

實作 0.6.0 時，以「設定內任一 MCP server 能在 `complete(..., tools=...)` 完成一輪 tool call」為驗收即可；其餘能力隨需求再加，不預先排進版本表。
