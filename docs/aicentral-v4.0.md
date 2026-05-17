# aicentral v4.0 — 多供應商、fallback 與 MCP

> 規格基線：[aicentral.md](./aicentral.md) · 上一版：[aicentral-v3.0.md](./aicentral-v3.0.md)  
> 參考實作（本 repo 內，**不安裝** `litellm` 套件）：[`litellm/litellm/`](../../litellm/litellm/)  
> 狀態：**規劃中**（本文件僅規格，不含程式實作）

---

## 一句話

v4.0 在 v2.0 的 `parse_model` + `providers/registry` 之上，**分別**實作 OpenAI、Anthropic（Claude）、Google Gemini 三類 **LLM provider**；並新增 **MCP 工具層**（參考 LiteLLM 的 `responses/mcp/` + `proxy/mcp_server/`，**不**當成第四個 LLM provider）。  
以 **`config/aicentral.yaml`**（或 env）驅動模型別名、金鑰、`base_url` 與簡易 **fallback**（例如 `ollama` 失敗 → `openai`）。

仍不實作：100+ provider、adaptive router、Proxy Admin UI、用量計費、guardrails 全套。

---

## 與 LiteLLM 的對照（設計參考）

| LiteLLM 路徑 | 職責 | aicentral v4.0 對應 |
|--------------|------|---------------------|
| `litellm/llms/openai/chat/` | OpenAI Chat Completions（含 Azure 等變體） | `providers/openai_cloud.py`（或拆分 `openai.py` 雲端專用） |
| `litellm/llms/anthropic/chat/` | Anthropic **Messages API**（`/v1/messages`），OpenAI 訊息 ↔ Anthropic 轉換 | `providers/anthropic.py` + `providers/transform/anthropic.py` |
| `litellm/llms/gemini/chat/` | Google AI Studio / Vertex Gemini，**非** OpenAI 格式 | `providers/gemini.py` + `providers/transform/gemini.py` |
| `litellm/llms/*` 的 `transformation.py` + `handler.py` | 請求組裝、回應解析、串流 | 各 provider 內 `*_request()` / `*_response()`，保持薄 adapter |
| `litellm/proxy/proxy_config.yaml` → `model_list` | 模型別名、`litellm_params`、env 金鑰 | `config/aicentral.yaml` → `model_list` |
| `litellm/proxy/proxy_config.yaml` → `mcp_servers` | MCP 連線定義（stdio / http / sse） | `config/aicentral.yaml` → `mcp_servers` |
| `litellm/responses/mcp/` | Responses / Chat Completions 與 MCP 工具編排 | `mcp/`（library 最小子集） |
| `litellm/proxy/_experimental/mcp_server/` | Proxy 端 MCP Client、OAuth、tool 前綴 | **v5.0 Gateway** 再擴；v4.0 library 只做 client + config |
| `litellm/router_strategy/` | fallback、負載 | `routing/router.py`（僅靜態 fallback 鏈） |

**閱讀建議**（本機原始碼）：

- OpenAI：`litellm/llms/openai/chat/gpt_transformation.py`
- Claude：`litellm/llms/anthropic/chat/transformation.py`、`handler.py`
- Gemini：`litellm/llms/gemini/chat/transformation.py`（繼承 Vertex Gemini 轉換）
- MCP 設定型別：`litellm/types/mcp.py`、`litellm/types/mcp_server/mcp_server_manager.py`
- MCP 與 Chat 整合：`litellm/responses/mcp/litellm_proxy_mcp_handler.py`、`chat_completions_handler.py`
- Proxy 設定範例：`litellm/proxy/proxy_config.yaml`（`model_list` + `mcp_servers`）

---

## MCP 應放在哪裡？（結論）

**不要**把 MCP 實作成 `providers/mcp.py` 並註冊進 `get_provider_module("mcp")`。

| 概念 | 說明 |
|------|------|
| **Provider（LLM）** | 產生文字／結構化回覆：OpenAI、Anthropic、Gemini、Ollama（OpenAI 相容） |
| **MCP** | 對外 **工具** 傳輸（list_tools / call_tool），透過 MCP 協定連到第三方 server |
| LiteLLM 作法 | MCP 在 **`responses/mcp/`** 與 **`proxy/.../mcp_server/`**，在 `completion` / `aresponses` 路徑上攔截 `tools` 裡 `type: "mcp"` 的項目 |
| aicentral v4.0 | 新增頂層 **`mcp/`**（或 `integrations/mcp/`），由 `core/client` 在偵測到 MCP 工具需求時委派；**不**經 `parse_model` 選 provider |

v4.0 **最小範圍**：設定檔載入 MCP server、`MCPClient` 連線、`list_tools` / `call_tool`；可選在 `complete(..., tools=[...])` 傳入 MCP 工具描述時，由 orchestrator 代為執行 tool loop（進階可延後至 v4.1）。

---

## 目錄結構（規劃）

```
src/aicentral/
├── config/
│   ├── __init__.py
│   ├── loader.py              # 讀 yaml + env 覆寫
│   └── schema.py              # Pydantic：ModelEntry、MCPServerEntry、RouterSettings
├── routing/
│   ├── parser.py              # 既有；擴充 provider 白名單
│   └── router.py              # fallback 鏈、model_list 別名解析
├── providers/
│   ├── registry.py            # ollama | openai | anthropic | gemini
│   ├── openai.py              # 既有：OpenAI 相容 HTTP（Ollama + 可共用邏輯）
│   ├── openai_cloud.py        # 可選：預設 api.openai.com（或 openai.py + profile）
│   ├── anthropic.py           # POST /v1/messages
│   ├── gemini.py              # Google Generative Language API
│   ├── transform/
│   │   ├── anthropic.py       # Message[] ↔ Anthropic messages
│   │   └── gemini.py          # Message[] ↔ Gemini contents/parts
│   └── base.py                # 既有 Protocol
├── mcp/
│   ├── __init__.py
│   ├── client.py              # stdio | http | sse 連線（參考 litellm experimental_mcp_client）
│   ├── manager.py             # 依 config 註冊多個 server、tool 名稱前綴
│   └── orchestrator.py        # 可選：complete 路徑上的 tool 執行迴圈
└── core/
    └── client.py              # complete 經 router 選路；MCP 分支
```

**依賴方向**：

```
complete / complete_structured
  → routing/router（別名 + fallback）
  → providers/*（LLM HTTP）
  → mcp/*（僅在 tools 含 MCP 時）
```

**禁止**：`providers/*` import `mcp/*` 的反向依賴；`mcp` 可呼叫 httpx，但不知道具體 LLM provider。

---

## LLM Providers 規格

### 1. OpenAI（雲端）

| 項目 | 說明 |
|------|------|
| LiteLLM 參考 | `llms/openai/chat/` |
| 協定 | `POST https://api.openai.com/v1/chat/completions`（可覆寫 `api_base`） |
| model 字串 | `openai/gpt-4o-mini` |
| 與現況 | 現有 `providers/openai.py` 已實作 OpenAI 相容 HTTP；v4.0 將 **Ollama** 與 **OpenAI 雲端** 在 registry 拆成不同 profile（見設定檔） |
| 實作要點 | `chat_completions` / `chat_completions_stream` / `chat_completions_raw`；金鑰自 config 或 `OPENAI_API_KEY` |
| v4.0 不做 | Assistants API、Batch、Realtime、Images（另版） |

### 2. Anthropic（Claude）

| 項目 | 說明 |
|------|------|
| LiteLLM 參考 | `llms/anthropic/chat/transformation.py`、`handler.py` |
| 協定 | `POST https://api.anthropic.com/v1/messages`（非 OpenAI 格式） |
| model 字串 | `anthropic/claude-sonnet-4-20250514`（`model_id` 為 Anthropic model name） |
| 轉換 | aicentral 統一 `Message(role, content)` → Anthropic `messages` + 可選 `system`；回應 `content[]` → 助理字串 |
| 結構化 | v3.0 `complete_structured` 需確認 Claude 的 tool / JSON 路徑；不支援時文件標註 `mode=json` 或僅 openai/ollama |
| 實作要點 | Header：`x-api-key`、`anthropic-version`；串流為 SSE 事件解析（可 P1 後補） |
| v4.0 不做 | Bedrock 上的 Claude（可 v4.x 另列 `bedrock` provider） |

### 3. Google Gemini

| 項目 | 說明 |
|------|------|
| LiteLLM 參考 | `llms/gemini/chat/transformation.py`、`llms/gemini/google_genai/` |
| 協定 | Google AI Studio：`generativelanguage.googleapis.com`（`v1beta` models `...:generateContent`） |
| model 字串 | `gemini/gemini-2.0-flash` |
| 轉換 | `Message[]` → `contents` + `parts`；`system` → `system_instruction` |
| 金鑰 | `GEMINI_API_KEY` 或 config `api_key`；query `?key=` 或 header（與 LiteLLM 對齊一種即可） |
| 實作要點 | `response_mime_type` / `response_schema` 對應 v3.0 `mode=json` 結構化 |
| v4.0 不做 | Vertex AI 專案 ID / GCP SA（可列 P2：`vertex` provider） |

### 4. Ollama（維持 v1.0 行為）

| 項目 | 說明 |
|------|------|
| 定位 | OpenAI 相容端點，`provider=ollama`，實作可 **重用** `providers/openai.py` |
| model 字串 | `ollama/gemma4:e2b` 或裸名 `gemma4:e2b` |
| 設定 | `OLLAMA_BASE_URL`、`OLLAMA_MODEL` 或 yaml `model_list` 條目 |

### Provider 註冊表（規劃）

```python
_REGISTRY = {
    "ollama": openai,       # base_url 來自 profile / env
    "openai": openai_cloud,
    "anthropic": anthropic,
    "gemini": gemini,
}
```

`parse_model("gpt-4o")` 在 v4.0 可改為：先查 `model_list` 別名 → 得到 `(provider, model_id)`；無別名時維持 v2.0 預設 `ollama`。

---

## MCP 規格（v4.0 最小集）

### 職責

1. 從 `config/aicentral.yaml` 的 `mcp_servers` 載入連線參數（對照 LiteLLM `proxy_config.yaml`）。
2. `MCPManager` 維護 `server_name → client`，支援 **stdio**、**http**、**sse**（對照 `litellm/types/mcp.py` 的 `MCPTransport`）。
3. 提供 `list_tools(server_name)`、`call_tool(server_name, name, arguments)`。
4. （P1）在 `complete` 收到 OpenAI 風格 `tools` 且含 MCP 宣告時，參考 `LiteLLM_Proxy_MCP_Handler._parse_mcp_tools` 分離 MCP 與一般 function tools。

### 不放在 providers 的原因（再述）

MCP server 不回傳 chat completion；它是 **工具後端**。LiteLLM 將 MCP 掛在 **Responses API / Proxy** 層，aicentral 對齊為獨立 **`mcp/`** 模組。

### Tool 宣告（消費方 / 未來 Gateway）

參考 LiteLLM Responses API 工具格式（簡化示意）：

```python
tools = [
    {
        "type": "mcp",
        "server_url": "aicentral/mcp/deepwiki",  # v4.0 內部別名，非真實 URL
        # 或對外 http MCP： "server_url": "https://mcp.example.com/mcp"
    },
    {"type": "function", "function": {...}},
]
```

v4.0 library 可只支援 **config 內 `server_name`** 引用（`server_url: "aicentral/mcp/<name>"`），不實作完整 public registry。

### v4.0 明確不做

- MCP OAuth2 / PKCE 全流程（LiteLLM Proxy 才有）
- `mcp_semantic_tool_filter`、guardrails
- `proxy/mcp_registry.json` 內建市集一鍵匯入（可手動抄 `mcp_servers` 條目）

---

## Routing 與 Fallback

參考 LiteLLM `litellm_settings.context_window_fallbacks` / Router 的 **靜態** fallback 鏈；v4.0 **不做** latency-based 或 cost-based 路由。

```yaml
router:
  fallbacks:
    - model_name: local-chat          # 別名
      fallbacks: [cloud-chat]         # 依序嘗試
  # 僅在下列錯誤時 fallback（建議）
  fallback_on:
    - connection_error
    - timeout
  # 不在此列表則直接拋出（例如 401、400）
```

行為：

1. `complete(model="local-chat", ...)` → 解析為 `ollama/...`。
2. 若 `ProviderError` 且符合 `fallback_on` → 改呼叫 `cloud-chat`（例如 `openai/gpt-4o-mini`）。
3. 用盡鏈結仍失敗 → 拋出最後一個錯誤（附 `attempted_models: list[str]` 可選）。

**重試**：與 v3.0 相同，**aicentral 不自動重試** validation；fallback 僅針對 **不同 model/provider**，非同一請求重複 N 次。

---

## 設定檔 `config/aicentral.yaml`

路徑搜尋順序（建議）：

1. 環境變數 `AICENTRAL_CONFIG` 指向的檔案  
2. `./aicentral.yaml`  
3. `./config/aicentral.yaml`  
4. 僅 env（與 v2.0 相容，無 yaml 亦可跑 Ollama）

金鑰支援 `os.environ/VAR_NAME` 前綴（對照 LiteLLM `litellm_params.api_key: os.environ/OPENAI_API_KEY`）。

### 完整範例

```yaml
# config/aicentral.yaml — aicentral v4.0 規劃範例

defaults:
  model: local-chat                    # model_list 別名
  timeout: 120
  structured_mode: tool                  # 覆寫 AICENTRAL_STRUCTURED_MODE

model_list:
  # --- Ollama（OpenAI 相容）---
  - model_name: local-chat
    provider: ollama
    params:
      model_id: gemma4:e2b
      api_base: os.environ/OLLAMA_BASE_URL   # 或 http://localhost:11434/v1
      api_key: os.environ/OLLAMA_API_KEY     # 可空

  # --- OpenAI 雲端 ---
  - model_name: cloud-chat
    provider: openai
    params:
      model_id: gpt-4o-mini
      api_base: https://api.openai.com/v1
      api_key: os.environ/OPENAI_API_KEY
    timeout: 60

  - model_name: cloud-chat-large
    provider: openai
    params:
      model_id: gpt-4o
      api_key: os.environ/OPENAI_API_KEY

  # --- Anthropic Claude ---
  - model_name: claude-sonnet
    provider: anthropic
    params:
      model_id: claude-sonnet-4-20250514
      api_base: https://api.anthropic.com
      api_key: os.environ/ANTHROPIC_API_KEY
      api_version: "2023-06-01"              # anthropic-version header

  # --- Google Gemini ---
  - model_name: gemini-flash
    provider: gemini
    params:
      model_id: gemini-2.0-flash
      api_key: os.environ/GEMINI_API_KEY
      # 可選：api_base 覆寫（Vertex 時不同）
      # api_base: https://generativelanguage.googleapis.com/v1beta

router:
  fallbacks:
    - model_name: local-chat
      fallbacks: [cloud-chat]
  fallback_on:
    - connection_error
    - timeout

mcp_servers:
  # 對照 litellm/proxy/proxy_config.yaml
  deepwiki:
    transport: http
    url: https://mcp.deepwiki.com/mcp
    description: "DeepWiki MCP"
    timeout: 30
    auth_type: none                        # none | bearer_token | api_key | ...
    # auth_value: os.environ/MCP_DEEPWIKI_TOKEN

  fetch:
    transport: stdio
    command: uvx
    args: ["mcp-server-fetch"]
    description: "Fetch web pages"
    env:
      # 子進程環境變數
      SOME_VAR: os.environ/SOME_VAR

  # sse 範例
  linear:
    transport: sse
    url: https://mcp.linear.app/sse
    auth_type: bearer_token
    auth_value: os.environ/LINEAR_API_KEY

mcp_settings:
  tool_name_prefix: true                   # server 前綴避免撞名（參考 LiteLLM）
  client_timeout: 30
  # allowed_servers: [deepwiki, fetch]     # 可選白名單

aicentral_settings:
  dev: false                               # 等同 AICENTRAL_DEV
  system_prompt: null                      # 覆寫 AICENTRAL_SYSTEM_PROMPT；null=用 env/內建
  drop_unsupported_params: true            # 參考 litellm drop_params
```

### `model_list` 欄位說明

| 欄位 | 必填 | 說明 |
|------|------|------|
| `model_name` | ✅ | 對外別名；`complete(model="local-chat")` |
| `provider` | ✅ | `ollama` \| `openai` \| `anthropic` \| `gemini` |
| `params.model_id` | ✅ | 送進該 provider API 的模型名 |
| `params.api_base` | 視 provider | OpenAI 相容 / Anthropic base |
| `params.api_key` | 建議 | 支援 `os.environ/...` |
| `params.api_version` | Anthropic | `anthropic-version` header |
| `timeout` | 否 | 覆寫全域 `defaults.timeout` |
| `stream_timeout` | 否 | 串流單 chunk 逾時（可 P1） |
| `rpm` / `tpm` | 否 | v4.0 **不實作** 限流，僅保留欄位供未來 Gateway |

### `mcp_servers` 欄位說明

| 欄位 | 必填 | 說明 |
|------|------|------|
| `transport` | ✅ | `stdio` \| `http` \| `sse` |
| `url` | http/sse | MCP endpoint |
| `command` | stdio | 執行檔，如 `uvx`、`npx` |
| `args` | stdio | 命令列參數 |
| `env` | 否 | stdio 子 process 環境變數 |
| `auth_type` | 否 | 對照 LiteLLM `MCPAuth` |
| `auth_value` | 否 | 支援 `os.environ/...` |
| `description` | 否 | 說明文字 |
| `timeout` | 否 | 連線 / list_tools 逾時 |
| `allowed_tools` | 否 | 工具白名單 |
| `disallowed_tools` | 否 | 工具黑名單 |
| `static_headers` | 否 | 轉發到 MCP HTTP 的固定 header |

---

## 環境變數（`.env` 對照）

在 [`.env.example`](../.env.example) 規劃追加（實作時一併更新範例檔）：

```env
# --- 設定檔路徑（v4.0）---
# AICENTRAL_CONFIG=./config/aicentral.yaml

# --- OpenAI 雲端 ---
OPENAI_API_KEY=
# OPENAI_API_BASE=https://api.openai.com/v1

# --- Anthropic ---
ANTHROPIC_API_KEY=
# ANTHROPIC_API_BASE=https://api.anthropic.com
# ANTHROPIC_API_VERSION=2023-06-01

# --- Google Gemini ---
GEMINI_API_KEY=
# GEMINI_API_BASE=https://generativelanguage.googleapis.com/v1beta

# --- MCP（依 server 自訂，範例）---
# MCP_DEEPWIKI_TOKEN=
# LINEAR_API_KEY=

# --- Router（可選，覆寫 yaml）---
# AICENTRAL_DEFAULT_MODEL=local-chat
```

既有 `OLLAMA_*`、`AICENTRAL_*`（v3.0）繼續有效；yaml 未設定時 fallback 到 env。

---

## 對外 API 變更（規劃）

### model 字串

```python
complete(messages, model="claude-sonnet")      # yaml 別名
complete(messages, model="anthropic/claude-sonnet-4-20250514")
complete(messages, model="gemini/gemini-2.0-flash")
complete(messages, model="openai/gpt-4o-mini")
complete(messages, model="ollama/gemma4:e2b")
```

### 可選：顯式 profile

```python
complete(..., model="gpt-4o", provider="openai", api_key="...")  # 覆寫 config，測試用
```

### MCP（P1 API 草案）

```python
from aicentral.mcp import MCPManager

mgr = MCPManager.from_config()  # 讀 aicentral.yaml
tools = mgr.list_tools("deepwiki")
result = mgr.call_tool("deepwiki", "search", {"query": "..."})
```

---

## 測試計畫

| 測試 | 內容 |
|------|------|
| `tests/providers/test_openai_cloud.py` | mock `api.openai.com` |
| `tests/providers/test_anthropic.py` | mock `/v1/messages` 請求體與回應轉換 |
| `tests/providers/test_gemini.py` | mock `generateContent` |
| `tests/routing/test_router.py` | fallback 鏈、別名解析 |
| `tests/config/test_loader.py` | yaml + `os.environ/` 展開 |
| `tests/mcp/test_manager.py` | mock stdio/http client |
| 整合 | 標記 `@pytest.mark.integration`，需真實 API key |

**不要求** CI 連真實雲端；手動驗收清單另列。

---

## 實作順序建議

| 階段 | 內容 | 優先 |
|------|------|------|
| P0 | `config/loader` + `model_list` + registry 擴充 `openai` 雲端 profile | 必須 |
| P0 | `providers/anthropic.py` + transform + mock 測試 | 必須 |
| P0 | `providers/gemini.py` + transform + mock 測試 | 必須 |
| P0 | `routing/router.py` 靜態 fallback | 必須 |
| P1 | `mcp/client` + `mcp/manager` + yaml `mcp_servers` | 建議 |
| P1 | `complete` 與 MCP tools 編排（最小 tool loop） | 建議 |
| P2 | Anthropic / Gemini 串流 | 可後補 |
| P2 | Vertex、Bedrock、Azure OpenAI | 不在 v4.0 |

---

## 驗收標準

- [ ] `model="openai/gpt-4o-mini"` 在設定 API key 後可回覆（mock 或整合測試）
- [ ] `model="anthropic/claude-..."` 走 Messages API，非 OpenAI URL
- [ ] `model="gemini/gemini-2.0-flash"` 走 Gemini API
- [ ] `local-chat` fallback 至 `cloud-chat` 在 Ollama 連線失敗時生效
- [ ] `mcp_servers` 可 `list_tools` / `call_tool`（至少一種 transport）
- [ ] v3.0 `complete_structured` 在 ollama/openai 路徑無回歸
- [ ] 既有 v2.0 裸 model 名稱仍指向 ollama

---

## 不在 v4.0 範圍

- LiteLLM Proxy、Virtual Keys、Admin UI
- 100+ `llms/*` provider
- Adaptive router、cost-based 路由
- MCP OAuth registry、semantic tool filter
- HTTP Gateway（見 [v5.0](./aicentral.md)）
- 修改消費方 `aicentral-chat` / `aicentral-structured-demo` 主流程（僅文件示範新 model 字串）

---

## 與版本路線圖

| 版本 | 關係 |
|------|------|
| v3.0 | `complete_structured` 已實作；v4.0 需標註各 provider 對 tool/json 的支援矩陣 |
| v5.0 | Gateway 可託管 `mcp_servers`、對外 `litellm_proxy` 式 MCP URL |

---

## 修訂紀錄

| 日期 | 說明 |
|------|------|
| 2026-05-17 | 擴充：OpenAI / Claude / Gemini providers、MCP 分層、config 欄位、LiteLLM 對照 |
