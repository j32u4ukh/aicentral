# aicentral v5.0 — 可選 HTTP Gateway

> 規格基線：[aicentral.md](./aicentral.md) · 上一版：[aicentral-v4.0.md](./aicentral-v4.0.md)  
> 公網／內網對外安全（Master Key、限流等）見 [security.md](./security.md)（**v5.0 不採用**，僅供日後若開放非本機綁定時參考）  
> 庫內選路（非 HTTP）：[routing.md](./routing.md)  
> 狀態：**規劃中**（本文件僅規格，實作隨 v5.0 里程碑展開）

---

## 一句話

v5.0 在 v4.0 函式庫之上，新增**可選**的 **HTTP Gateway**：僅供 **localhost** 使用，以 **OpenAI Chat Completions 相容協定**（含串流 SSE）在本機傳遞請求與回應，支援**文字與圖片**等多模態 `content`；對內**只委派** `core.complete()` / `routing`。  
讓**同一台機器**上的非 Python 程式、本機腳本與工具（curl、OpenAI SDK 等）能連到 aicentral，**不**設計成對區網或公網暴露的服務。

---

## 部署範圍：僅 localhost（硬性）

v5.0 Gateway 的**產品邊界**是「本機程序間的 OpenAI 相容 HTTP」，不是 LiteLLM Proxy 式的對外 API。

| 原則 | 規格 |
|------|------|
| **只聽 loopback** | `bind_host` 僅允許 `127.0.0.1` 或 `::1`；**禁止** `0.0.0.0`、`::`、區網 IP |
| **啟動時拒絕** | 設定或 CLI 若指定非 loopback → **程序退出**並印出明確錯誤 |
| **不對外宣稱安全** | 不依賴 Master Key / Virtual Key 作為 v5.0 必要條件（見下方「本機安全」） |
| **客戶端也限本機** | 文件與範例一律使用 `http://127.0.0.1:8080`；不教學用區網 IP 呼叫 |
| **與 Ollama 一致** | Ollama 亦應只聽本機；Gateway 是第二層，**不**取代「勿把 11434 暴露公網」的建議 |

```
┌─────────────────────────────────────────┐
│  本機（同一台機器）                       │
│  ┌─────────┐   loopback    ┌──────────┐ │
│  │ curl /  │ ────────────► │ Gateway  │ │
│  │ OpenAI  │  127.0.0.1    │ :8080    │ │
│  │ SDK     │               └────┬─────┘ │
│  └─────────┘                    │       │
│                                 ▼       │
│                          core.complete  │
│                                 │       │
│                                 ▼       │
│                          Ollama :11434  │
└─────────────────────────────────────────┘
         ✕ 不接收來自區網/網際網的連線
```

> 若日後需要讓**其他機器**呼叫，應視為**新版本或獨立模式**，並啟用 [security.md](./security.md) 的 S1～S2；**不在 v5.0 範圍內**。

### 部署方式（v5.0）

| 方式 | 說明 |
|------|------|
| **建議** | `pip install "aicentral[gateway]"` 後 `python -m aicentral.gateway`（或 uvicorn，`--host 127.0.0.1`） |
| **Docker** | **v5.0 不實作、不驗收**；repo 內既有 `docker/` 與 LiteLLM 等用途相關，**非**本版 Gateway 交付範圍。若日後需要容器化，另開規格。 |

---

## 目標與非目標

### 要做

| 項目 | 說明 |
|------|------|
| **統一對外協定** | OpenAI `POST /v1/chat/completions`（JSON body + 可選 `stream: true`） |
| **多模態輸入** | `messages[].content` 支援字串或 **content parts**（`text`、`image_url`） |
| **與庫一致的路由** | `model` 字串 / yaml 別名 → v4 `resolve_call` / fallback |
| **本機隔離** | 僅 bind loopback + 可選「客戶端 IP 必須為本機」middleware |
| **請求大小上限** | 防本機惡意/錯誤腳本送超大 body |
| **本機安裝啟動** | `pip install "aicentral[gateway]"` |
| **健康檢查** | `GET /health`（僅本機可達） |

### 不做（v5.0）

| 項目 | 延後／不採 |
|------|------------|
| **對區網／公網暴露** | 不支援 `0.0.0.0`、不提供「對外模式」 |
| **Master Key / Virtual Key 必填** | 不採；可選 `gateway.optional_token` 見下方 |
| **RPM 限流、IP 白名單（S2）** | 本機場景效益低；若未來開放非 loopback 再參考 security.md |
| **Gateway 的 Docker / Compose 交付** | 不納入 v5.0；見上方「部署方式」 |
| Embeddings / Images 生成 / Audio / Batch | v5.x 或不做 |
| 100+ provider、adaptive router | 不採 |
| Admin UI、Prisma、完整計費後台 | 不採 |
| MCP tool loop 自動編排在 Gateway 內 | v5.1+ |
| `POST /v1/responses` | 可選 v5.2 |
| 所有 provider 都支援 vision | 依後端；不支援時 **400** |

---

## 為何選 OpenAI Chat Completions 作為「統一協定」

| 理由 | 說明 |
|------|------|
| **生態成熟** | 官方 SDK、LangChain、Postman 等皆支援 |
| **與 v1.0 一致** | Ollama 本機即 OpenAI 相容；v4 provider 多數可映射同一請求形狀 |
| **單一端點可涵蓋文字 + 圖片** | `content` 陣列 parts 為業界事實標準 |
| **串流標準化** | `stream: true` → `text/event-stream`，`data: {...}` 行格式 |

**內部分層**（與 [aicentral.md](./aicentral.md) 一致）：

```
外部客戶端  ──OpenAI JSON──►  gateway/（協定轉換、本機檢查）
                              │
                              ▼
                         core.complete()  ──►  routing  ──►  providers/*
```

Gateway 負責 **HTTP ↔ 內部 Message**；`providers/` 負責 **內部 Message ↔ 各供應商實際 HTTP**。

---

## 統一資料模型（對外）

### 請求：`POST /v1/chat/completions`

與 [OpenAI Chat Completions](https://platform.openai.com/docs/api-reference/chat/create) 對齊之**必要子集**：

| 欄位 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `model` | string | ✅ | `ollama/gemma4:e2b`、`local-chat`（yaml 別名）等；未傳時 Gateway **拒絕**（HTTP 400），不自行猜預設 |
| `messages` | array | ✅ | 對話歷史；見下方 **Message** |
| `stream` | boolean | 否 | 預設 `false`；`true` 時回 SSE |
| `temperature` | number | 否 | 轉傳 provider（不支援則忽略） |
| `max_tokens` | integer | 否 | 同上 |
| `tools` / `tool_choice` | — | 否 | v5.0 **可選**；見 v5.1 |

**Message**（單則）：

| 欄位 | 說明 |
|------|------|
| `role` | `system` \| `user` \| `assistant` |
| `content` | **字串**（純文字）或 **ContentPart 陣列**（多模態） |

### ContentPart（多模態）

#### 1. 文字 — `type: "text"`

```json
{ "type": "text", "text": "請描述這張圖片" }
```

#### 2. 圖片 — `type: "image_url"`

```json
{
  "type": "image_url",
  "image_url": {
    "url": "https://example.com/photo.jpg",
    "detail": "auto"
  }
}
```

或 **Base64 data URL**（單檔上限見 `gateway.max_image_bytes`）：

```json
{
  "type": "image_url",
  "image_url": {
    "url": "data:image/jpeg;base64,/9j/4AAQSkZJRg..."
  }
}
```

| 子欄位 | 說明 |
|--------|------|
| `url` | `http(s)://...` 或 `data:image/{format};base64,...` |
| `detail` | `auto` \| `low` \| `high`（轉傳支援 vision 的 provider） |

#### 3. v5.0 明確不支援（收到即 400）

| type | 說明 |
|------|------|
| `input_audio` | 音訊 → v5.x |
| `file` | PDF 等 → v5.x |

**混合範例**：

```json
{
  "role": "user",
  "content": [
    { "type": "text", "text": "圖裡有什麼？" },
    {
      "type": "image_url",
      "image_url": { "url": "data:image/png;base64,iVBORw0KGgo..." }
    }
  ]
}
```

### 回應：非串流

```json
{
  "id": "chatcmpl-ac-...",
  "object": "chat.completion",
  "created": 1710000000,
  "model": "local-chat",
  "choices": [
    {
      "index": 0,
      "message": { "role": "assistant", "content": "圖中是一隻貓。" },
      "finish_reason": "stop"
    }
  ],
  "usage": { "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0 }
}
```

> 底層無 token 計數時，`usage` 可填 `0` 或省略。

### 回應：串流（`stream: true`）

- `Content-Type: text/event-stream`
- 每行 `data: {"object":"chat.completion.chunk",...,"choices":[{"delta":{"content":"..."}}]}`
- 結束：`data: [DONE]`

Gateway 將 `core.complete(..., stream=True)` **逐 delta 映射**為 OpenAI chunk。

### 錯誤回應

| HTTP | `error.type`（建議） | 情境 |
|------|----------------------|------|
| 400 | `invalid_request_error` | 缺 `model`、不支援的 content type、圖片過大 |
| 401 | `authentication_error` | 僅在啟用 `gateway.optional_token` 且未帶／錯誤 Bearer 時 |
| 403 | `access_denied` | 客戶端 IP 非 loopback |
| 413 | `invalid_request_error` | body 超過 `gateway.max_body_bytes` |
| 429 | `rate_limit_error` | 僅未來「對外模式」 |
| 502 | `api_error` | provider 連線失敗 |
| 504 | `timeout_error` | 逾時 |

格式：`{"error":{"message":"...","type":"...","code":null}}`。

---

## 內部型別擴充（相對 v4）

目前 `core/types.py` 的 `Message.content` 僅 `str`。v5.0 規劃：

```python
ContentPart = TextPart | ImageUrlPart

class Message(TypedDict):
    role: Role
    content: str | list[ContentPart]
```

| 層級 | 職責 |
|------|------|
| `gateway/schemas.py` | Pydantic：驗證對外 OpenAI JSON、大小與 MIME |
| `gateway/convert.py` | OpenAI Message[] → 內部 Message[] |
| `providers/transform/*` | 內部 parts → Anthropic/Gemini/Ollama |
| `providers/openai.py` | OpenAI 形狀可直通 |

**Vision 能力矩陣**：

| Provider | 圖片輸入 | 備註 |
|----------|----------|------|
| OpenAI 雲端 | ✅ | `gpt-4o` 等 |
| Anthropic | ✅ | Claude 3+ |
| Gemini | ✅ | `gemini-*-flash` 等 |
| Ollama | ⚠️ 依模型 | `llava` 等；不支援時 **400** |

---

## 架構與模組

```
src/aicentral/gateway/
├── __init__.py
├── app.py              # FastAPI、lifespan、bind 驗證（僅 loopback）
├── localhost.py        # 啟動檢查 bind_host；middleware 拒絕非本機 client IP
├── middleware.py       # body 大小、逾時、請求 ID（無 CORS 預設）
├── schemas.py          # 對外 OpenAI 請求/回應 Pydantic
├── convert.py          # OpenAI ↔ core Message、stream chunk 組裝
├── auth.py             # 可選：optional_token（預設關閉）
├── routes/
│   ├── health.py       # GET /health
│   └── chat.py         # POST /v1/chat/completions
└── server.py           # uvicorn 啟動（強制 --host 127.0.0.1）
```

**依賴方向**：

```
localhost 檢查 → middleware（大小/IP）→ [optional auth] → routes/chat → core.complete()
```

**v5.0 不實作** `keys.py`、`rate_limit.py`（留待日後「對外模式」）。

### 與 v4 Router 的關係

| 概念 | v4（庫內） | v5（Gateway） |
|------|------------|----------------|
| 選 model / provider | `routing/router.py` | 讀 body `model`，同一套 `resolve_call` |
| Fallback | `complete_with_fallback` | 預設與庫相同 |
| 設定來源 | `config/aicentral.yaml` + `secret.yaml` | 啟動時 `load_config()` |
| MCP | `mcp/` | v5.0 不暴露 HTTP；v5.1+ |

---

## 設定（YAML）

```yaml
# config/aicentral.yaml（節錄）
gateway:
  enabled: true
  bind_host: 127.0.0.1
  bind_port: 8080
  localhost_only: true
  reject_non_local_client: true
  max_body_bytes: 20971520
  max_image_bytes: 10485760
  allowed_image_mime: [image/jpeg, image/png, image/webp, image/gif]
  fetch_remote_images: false
  optional_token: null
  default_model: local-chat   # 文件用；HTTP 仍要求客戶端傳 model

# config/secret.yaml（可選）
# gateway:
#   optional_token: "dev-local-only"
```

| 設定 | 說明 |
|------|------|
| `bind_host` | 僅 loopback；非 loopback → 啟動失敗 |
| `reject_non_local_client` | 非 `127.0.0.1`/`::1` → 403；不看 `X-Forwarded-For` |
| `optional_token` | 非 null 時才要 Bearer |
| `fetch_remote_images` | 預設 false（防 SSRF） |

---

## 本機安全（v5.0 簡化模型）

v5.0 **不**實作 [security.md](./security.md) S1/S2；以**網路隔離**為主：

### 第一層：只 bind loopback（必要）

| 措施 | 行為 |
|------|------|
| 預設 `127.0.0.1:8080` | 可改 port，不可改為 `0.0.0.0` |
| 設定檔防呆 | 非 loopback `bind_host` → **exit 1** |
| CLI 防呆 | 官方入口啟動時拒絕 `--host 0.0.0.0` |

### 第二層：拒絕非本機客戶端（建議）

| 措施 | 行為 |
|------|------|
| `reject_non_local_client: true` | 非 loopback client → **403** |

### 第三層：應用層（精簡）

| 措施 | 行為 |
|------|------|
| 預設免 Bearer | 本機程序可直接呼叫 |
| 可選 token | `optional_token` 啟用時未帶 → 401 |
| body / 圖片上限 | 防錯誤與惡意本機程序 |
| 不開 CORS | 瀏覽器請走後端代理 |
| 日誌 | 不記錄完整 base64 與 token |

### 明確排除的外部連線情境

| 情境 | v5.0 態度 |
|------|-----------|
| 區網他機連本機區網 IP | **不支援**（未 listen） |
| `bind 0.0.0.0` | **禁止** |
| frp / ngrok | **不支援** |
| Windows 防火牆 | 建議阻擋入站 8080 |

### 與 security.md 的關係

| 文件 | v5.0 |
|------|------|
| [security.md](./security.md) S1～S4 | **不套用** |
| 未來「對外模式」 | 非 loopback + Master Key + S2 |

**驗收（本機安全）**：

- [ ] 非 loopback `bind_host` 無法啟動
- [ ] 僅見 `127.0.0.1:8080`（或 `::1`）
- [ ] 區網他機連不上
- [ ] 本機 `curl 127.0.0.1` 成功

---

## 如何使用這個伺服器

### 1. 安裝

```powershell
cd aicentral
Copy-Item config\secret.yaml.example config\secret.yaml
pip install -e ".[gateway]"
```

### 2. 啟動

```powershell
python -m aicentral.gateway
# 或：uvicorn aicentral.gateway.app:app --host 127.0.0.1 --port 8080
```

確認 Ollama（或 yaml 指向的雲端）可用；啟動後確認僅 listen loopback。

### 3. 健康檢查

```bash
curl http://127.0.0.1:8080/health
```

### 4. 純文字對話

```bash
curl http://127.0.0.1:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"local-chat","messages":[{"role":"user","content":"你好"}]}'
```

### 5. 串流

```bash
curl http://127.0.0.1:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"local-chat","messages":[{"role":"user","content":"你好"}],"stream":true}' \
  --no-buffer
```

### 6. 文字 + 圖片（Base64）

```json
{
  "model": "cloud-chat",
  "messages": [{
    "role": "user",
    "content": [
      { "type": "text", "text": "描述這張圖" },
      { "type": "image_url", "image_url": { "url": "data:image/jpeg;base64,..." } }
    ]
  }]
}
```

### 7. Python（OpenAI SDK）

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:8080/v1",
    api_key="not-needed",
)
r = client.chat.completions.create(
    model="local-chat",
    messages=[{"role": "user", "content": "你好"}],
)
print(r.choices[0].message.content)
```

### 8. 其他語言 / 工具

同機上任何 OpenAI 相容客戶端，指定 `base_url=http://127.0.0.1:8080/v1` 即可。

### 9. 與「直接 import 函式庫」的選擇

| 情境 | 建議 |
|------|------|
| 同機 Python（如 `aicentral-chat`） | `Chat` / `complete()`，不經 HTTP |
| 同機其他語言 | Gateway |
| 他機／瀏覽器直連 | v5.0 **不支援** |

---

## 分階段交付

| 階段 | 內容 | 驗收 |
|------|------|------|
| **v5.0-alpha** | loopback + 純文字非串流 | 本機 curl 可對話 |
| **v5.0-beta** | SSE 串流 | 逐字輸出 |
| **v5.0** | 多模態、body 上限、reject_non_local_client | vision 圖文 |
| **v5.1** | tools、MCP HTTP | 見 [mcp.md](./mcp.md) |
| **v5.2** | `fetch_remote_images`、structured HTTP（可選） | — |

---

## 套件與部署產出

| 產出 | 說明 |
|------|------|
| `src/aicentral/gateway/` | FastAPI 應用與路由 |
| `pip install "aicentral[gateway]"` | fastapi、uvicorn |
| `python -m aicentral.gateway` | CLI 啟動 |
| `tests/gateway/` | 契約、SSE、本機隔離測試 |

> **Docker**：不列入 v5.0 產出；開發與驗收以本機 `pip install` + `python -m aicentral.gateway` 為準。

---

## 測試策略

| 類型 | 內容 |
|------|------|
| **契約測試** | 文字 / 多模態 / 400 |
| **整合測試** | TestClient + mock `complete()` |
| **串流測試** | SSE 至 `[DONE]` |
| **本機隔離測試** | 非 loopback bind 失敗、403 client IP |

---

## 驗收清單（v5.0 GA）

- [ ] OpenAI SDK / curl 本機可對話與串流
- [ ] vision base64 可用；不支援 vision 的 model → 400
- [ ] 僅 listen loopback；`0.0.0.0` 無法啟動
- [ ] 區網他機連不上
- [ ] 只委派 `core.complete()`
- [ ] 設定來自 `config/*.yaml`
- [ ] 預設不需 `Authorization`

---

## 與其他文件的關係

| 文件 | 關係 |
|------|------|
| [routing.md](./routing.md) | 庫內 Router ≠ Gateway |
| [security.md](./security.md) | 僅未來對外模式 |
| [mcp.md](./mcp.md) | MCP HTTP 延後 v5.1 |
| [aicentral-v4.0.md](./aicentral-v4.0.md) | v5 前置 |
| [concepts.md](./concepts.md) | `complete()` 語意不變 |

---

## 小結

| 問題 | 答案 |
|------|------|
| 統一協定？ | OpenAI Chat Completions + 可選 SSE |
| 圖片？ | `content` 的 `image_url`（建議 base64） |
| 誰能連？ | 僅本機 `127.0.0.1` |
| 需要 API Key？ | 預設不需要；可選 `optional_token` |
| 怎麼部署？ | `pip install "aicentral[gateway]"` → 本機啟動（**不用 Docker**） |
| 與 import？ | 並存；同機 Python 優先 import |

實作順序：**loopback → 純文字 → 串流 → 多模態**。
