# aicentral 專案架構

> 參考：[litellm.md](./litellm.md)、[instructor.md](./instructor.md)  
> 概念說明（`complete()` 用途等）：[concepts.md](./concepts.md)  
> Proxy 使用：[proxy.md](./proxy.md) · MCP 使用：[mcp.md](./mcp.md)  
> 定位：輕量化合併 LiteLLM（統一呼叫）與 Instructor（結構化輸出）的設計思想，**不依賴** `litellm` / `instructor` 套件。

**套件版本**以 [`pyproject.toml`](../pyproject.toml) 的 `version` 為準（目前 **0.6.1**）。下文「0.x」指套件 semver，與早期文件中的「v1.0～v5.0 里程碑」不同；歷史里程碑說明見文末連結。

---

## 專案定位

**aicentral 是提供給其他專案使用的 AI 能力函式庫（library）**，不是承載業務的應用服務：

- ✅ 對外提供 `complete()`、`complete_structured()`、`Chat` 等，由消費方 `import` 使用
- ✅ 可選 **HTTP Proxy**（`pip install "aicentral[gateway]"`、`python -m aicentral.gateway`）
- ✅ 可選 **MCP 工具層**（`pip install "aicentral[mcp]"`、`MCPManager`）
- ❌ 不在此 repo 封裝業務 API、領域 model、workflow
- ❌ 業務邏輯放在**消費方專案**（例如 [`aicentral-chat`](../../aicentral-chat)、[`aicentral-mcp`](../../aicentral-mcp)）

```
aicentral-chat / aicentral-mcp / 你的後端
        │
        ├─ import：complete / Chat / complete_structured
        ├─ HTTP：POST /v1/chat/completions（本機 Proxy）
        └─ MCP：MCPManager、complete(mcp_servers=...)
        ▼
   aicentral（能力層）
        │
        ├─ routing → providers（Ollama / OpenAI / Anthropic / Gemini）
        └─ mcp/（外部工具，非 LLM）
```

---

## 目前已交付能力（0.6.0）

| 領域 | 模組 / API | 說明 |
|------|------------|------|
| 對話 | `complete()`、`Chat` | 統一 messages、串流、繁中語系等 |
| 結構化 | `complete_structured()`、`structured/*` | Pydantic 驗證與重試 |
| 路由 | `routing/parser`、`routing/router` | `provider/model`、yaml `model_list`、fallback |
| 設定 | `config/loader`、`config/schema` | `config/aicentral.yaml` + `config/secret.yaml` |
| 供應商 | `providers/*` | Ollama（OpenAI 相容）、OpenAI、Anthropic、Gemini |
| MCP | `mcp/client`、`mcp/manager`、`mcp/registry`、`mcp/orchestrator` | `list_tools` / `call_tool`；`complete(mcp_servers=...)` tool loop |
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
python chat.py              # import Chat
python chat_http.py         # HTTP Proxy
cd ..\aicentral-mcp
pip install -e .
python example_02_complete_mcp.py   # complete + MCP 編排
```

---

## 目錄結構

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

| 消費方專案 | 用途 |
|------------|------|
| [`aicentral-chat`](../../aicentral-chat) | 終端對話：`chat.py`（`Chat`）、`chat_http.py`（Proxy） |
| [`aicentral-mcp`](../../aicentral-mcp) | **MCP 專用**：Import（`Chat.with_mcp`）與 HTTP（`/v1/mcp/*`）兩套範例 |
| [`unity-mcp`](../../unity-mcp) | **Unity MCP**：執行期註冊 server；`build_goals.yaml` + LangGraph 依序建構（`unity-mcp-build`） |
| [`aicentral-agent`](../../aicentral-agent) | **LangGraph**：`ChatAicentral` 適配器 + 圖／ReAct 編排，LLM 經 aicentral |

**禁止**在消費方直接 `httpx` 打 Ollama 或繞過 aicentral 的路由／設定。

---

## 與上游概念的對照

| 上游 | aicentral 模組 | 狀態 |
|------|----------------|------------|
| LiteLLM `completion()` | `complete()` | ✅ |
| LiteLLM `llms/*` | `providers/*` | ✅ |
| LiteLLM `router_strategy/*` | `routing/*` | ✅ |
| Instructor `response_model` | `complete_structured()` + `structured/*` | ✅ |
| LiteLLM `proxy/*` | `gateway/*`（本機） | ✅ |
| LiteLLM `responses/mcp/` | `mcp/*` | ✅ client + `complete(mcp_servers=...)` 編排 |
| 業務 / 對話 UI | **消費方**（`aicentral-chat`、`aicentral-mcp` 等） | ✅ |

---

## MCP 里程碑（0.6.x）

| 版本 | 目標 | 狀態 |
|------|------|------|
| **0.6.0** | Library：`Chat.with_mcp` / `complete(mcp_servers=...)` tool loop | ✅ [aicentral-v0.6.0.md](./aicentral-v0.6.0.md) |
| **0.6.1** | Proxy HTTP：`/v1/mcp/servers` + `/v1/mcp/{server}/tools` | ✅ [aicentral-v0.6.1.md](./aicentral-v0.6.1.md) |

其餘 MCP 進階能力**不預排版本**。

**認證**：`auth_type: none` / `bearer_token` / `basic` + `secret.yaml` 靜態 token，無需 OAuth 模組即可接多數遠端 MCP。

### 刻意不做（非延後，保持輕量）

以下**不在路線圖**；若日後确有需求再單独立項，避免預先膨脹函式庫：

| 項目 | 說明 |
|------|------|
| MCP OAuth2 / PKCE 全流程 | 靜態 bearer 已可接多數服務；OAuth 由消費方或 IDE 處理 |
| `mcp_semantic_tool_filter`、registry 市集一鍵匯入 | LiteLLM 進階能力；非 MVP |
| MCP 專用可觀測／metrics 平台 | 先用應用層日誌；有需要再加 |
| Gateway 對外網開放 MCP | 與本機 Proxy 定位不符 |

### 0.6.0 — `complete()` 與 MCP 編排（已交付）

> 規格與驗收見 **[aicentral-v0.6.0.md](./aicentral-v0.6.0.md)**；可執行範例見 **[aicentral-mcp](../../aicentral-mcp)**（`example_01`～`example_04`）。

```
complete(messages, mcp_servers=["deepwiki"])
  → mcp/orchestrator：list_tools → OpenAI tools
  → 模型 tool_calls → MCPManager.call_tool → role: tool
  → 迴圈直至文字或 max_tool_rounds（MCPError 不觸發 LLM fallback）
```

| 項目 | 說明 |
|------|------|
| 設定 | `mcp_servers`、`mcp_settings`；`register_mcp_server()` |
| 依賴 | `pip install "aicentral[mcp]"` |
| 限制 | MCP loop **不支援** `stream=True` |

### 0.6.1 — Proxy 與 MCP HTTP（已交付）

> 完整 HTTP 契約、curl／[`aicentral-mcp`](../../aicentral-mcp) 見 **[aicentral-v0.6.1.md](./aicentral-v0.6.1.md)**、[proxy.md](./proxy.md)。

本機 Gateway REST：

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

### 消費方範例

| 專案 | 腳本 | 說明 |
|------|------|------|
| `aicentral-chat` | `chat.py`、`chat_http.py` | 純對話（import / Proxy） |
| `aicentral-mcp` | `example_*`、`example_http_*` | MCP：Import + HTTP 兩套 |

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
| 目前版本？ | **0.6.1**（見 `pyproject.toml`） |
| 現在能做什麼？ | 多供應商對話、結構化輸出、MCP tool loop、Proxy MCP HTTP、本機 Chat Proxy |
| 下一步做什麼？ | 依需求在消費方擴充；無預排 MCP 版本 |
| 業務放哪？ | **消費方專案**，不在 aicentral |
| MCP 是 LLM 嗎？ | **否**；獨立 `mcp/` 模組，不經 `parse_model` 選 provider |

MCP 可選 **import**（`Chat.with_mcp`）或 **HTTP**（`/v1/mcp/*`）；其餘能力隨需求在消費方擴充。
