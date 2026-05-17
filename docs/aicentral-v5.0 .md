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
│  本機（同一台機器）                        │
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

---

## 目標與非目標

### 要做

| 項目 | 說明 |
|------|------|
| **統一對外協定** | OpenAI `POST /v1/chat/completions`（JSON body + 可選 `stream: true`） |
| **多模態輸入** | `messages[].content` 支援字串或 **content parts**（`text`、`image_url`） |
| **與庫一致的路由** | `model` 字串 / yaml 別名 → v4 `resolve_call` / fallback |
| **本機隔離** | 僅 bind loopback + 可選「客戶端 IP 必須為本機」middleware |
| **請求大小上限** | 防本機惡意/錯誤腳本送超大 body（與是否對外無關） |
| **可選部署** | `pip install "aicentral[gateway]"`；Docker 若使用須仍映射到 `127.0.0.1` |
| **健康檢查** | `GET /health`（僅本機可達） |

### 不做（v5.0）

| 項目 | 延後／不採 |
|------|------------|
| **對區網／公網暴露** | 不支援 `0.0.0.0`、不提供「對外模式」 |
| **Master Key / Virtual Key 必填** | 不採；可選 `gateway.optional_token` 見下方 |
| **RPM 限流、IP 白名單（S2）** | 本機場景效益低；若未來開放非 loopback 再參考 security.md |
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
| **生態成熟** | 官方 SDK、LangChain、LiteLLM Proxy 客戶端、Postman 範本皆支援 |
| **與 v1.0 一致** | Ollama 本機即 OpenAI 相容；v4 provider 多數可映射同一請求形狀 |
| **單一端點可涵蓋文字 + 圖片** | `content` 陣列 parts 為業界事實標準（OpenAI / 多數相容層） |
| **串流標準化** | `stream: true` → `text/event-stream`，`data: {...}` 行格式 |

**內部分層**（與 [aicentral.md](./aicentral.md) 一致）：

```
外部客戶端  ──OpenAI JSON──►  gateway/（驗證、限流、協定轉換）
                              │
                              ▼
                         core.complete()  ──►  routing  ──►  providers/*
```

Gateway 負責 **HTTP ↔ 內部 Message**；`providers/` 負責 **內部 Message ↔ 各供應商實際 HTTP**（Anthropic Messages、Gemini generateContent 等）。

---

## 統一資料模型（對外）

### 請求：`POST /v1/chat/completions`

與 [OpenAI Chat Completions](https://platform.openai.com/docs/api-reference/chat/create) 對齊之**必要子集**：

| 欄位 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `model` | string | ✅ | `ollama/gemma4:e2b`、`local-chat`（yaml 別名）等；未傳時 Gateway **拒絕**（HTTP 400），不自行猜預設 |
| `messages` | array | ✅ | 對話歷史；見下方 **Message** |
| `stream` | boolean | 否 | 預設 `false`；`true` 時回 SSE |
| `temperature` | number | 否 | 轉傳 provider（不支援則忽略，見 `drop_unsupported_params`） |
| `max_tokens` | integer | 否 | 同上 |
| `tools` / `tool_choice` | — | 否 | v5.0 **可選**；結構化 tool 與 MCP 編排見 v5.1 |

**Message**（單則）：

| 欄位 | 說明 |
|------|------|
| `role` | `system` \| `user` \| `assistant`（v5.0 不暴露 `tool` 角色於對外 API，tool 結果以 v5.1 擴充） |
| `content` | **字串**（純文字）或 **ContentPart 陣列**（多模態） |

### ContentPart（多模態）

v5.0 支援下列 part 類型（對齊 OpenAI）：

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

或 **Base64 data URL**（建議單檔上限於 Gateway 設定，例如 10MB decoded）：

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
| `detail` | `auto` \| `low` \| `high`（轉傳支援 vision 的 provider；否則忽略） |

#### 3. v5.0 明確不支援（收到即 400）

| type | 說明 |
|------|------|
| `input_audio` | 音訊輸入 → v5.x 再議 |
| `file` | PDF 等檔案 → v5.x 再議 |
| 自訂 embedding blob | 非 OpenAI 標準 |

**混合範例**（一則 user 訊息同時含文字與圖）：

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

OpenAI 形狀（精簡）：

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
  "usage": {
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "total_tokens": 0
  }
}
```

> v5.0 若底層無 token 計數，`usage` 可填 `0` 或省略（文件註明）；S3 用量估算見 [security.md](./security.md)。

### 回應：串流（`stream: true`）

- `Content-Type: text/event-stream`
- 每行 `data: {"id":"...","object":"chat.completion.chunk",...,"choices":[{"delta":{"content":"..."}}]}`
- 結束：`data: [DONE]`

Gateway 將 `core.complete(..., stream=True)` 的迭代器**逐 delta 映射**為 OpenAI chunk；不另寫 provider 串流邏輯。

### 錯誤回應

| HTTP | `error.type`（建議） | 情境 |
|------|----------------------|------|
| 400 | `invalid_request_error` | 缺 `model`、不支援的 content type、圖片過大 |
| 401 | `authentication_error` | 僅在啟用 `gateway.optional_token` 且未帶／錯誤 Bearer 時 |
| 403 | `access_denied` | 客戶端 IP 非 loopback（見本機安全） |
| 413 | `invalid_request_error` | body 超過 `gateway.max_body_bytes` |
| 429 | `rate_limit_error` | 僅未來「對外模式」；v5.0 本機版不實作 |
| 502 | `api_error` | provider 連線失敗（可含 `failure_kind` 於 message，不洩漏金鑰） |
| 504 | `timeout_error` | 逾時 |

格式對齊 OpenAI：`{"error":{"message":"...","type":"...","code":null}}`。

---

## 內部型別擴充（相對 v4）

目前 `core/types.py` 的 `Message.content` 僅 `str`。v5.0 規劃：

```python
# 概念（實作時放 core/types.py 或 gateway/schemas.py）
ContentPart = TextPart | ImageUrlPart

class Message(TypedDict):
    role: Role
    content: str | list[ContentPart]
```

| 層級 | 職責 |
|------|------|
| `gateway/schemas.py` | Pydantic：驗證對外 OpenAI JSON、大小與 MIME |
| `gateway/convert.py` | OpenAI Message[] → 內部 Message[] |
| `providers/transform/*` | 內部 parts → Anthropic/Gemini/Ollama 各自格式 |
| `providers/openai.py` | 已是 OpenAI 形狀時可直通 |

**Vision 能力矩陣**（規劃期聲明，實作時寫入文件）：

| Provider | 圖片輸入 | 備註 |
|----------|----------|------|
| OpenAI 雲端 | ✅ | `gpt-4o` 等 |
| Anthropic | ✅ | Claude 3+ |
| Gemini | ✅ | `gemini-*-flash` 等 |
| Ollama | ⚠️ 依模型 | `llava` 等支援；不支援時 **400** + 明確訊息 |

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

**依賴方向**（強制）：

```
localhost 檢查 → middleware（大小/IP）→ [optional auth] → routes/chat → core.complete()
```

禁止在 `providers/` 或 `complete()` 內做 HTTP 層安全邏輯。  
**v5.0 不實作** `keys.py`、`rate_limit.py`（留待日後「非本機模式」）。

### 與 v4 Router 的關係

| 概念 | v4（庫內） | v5（Gateway） |
|------|------------|----------------|
| 選 model / provider | `routing/router.py` | 讀請求 body 的 `model`，呼叫同一套 `resolve_call` |
| Fallback | `complete_with_fallback` | Gateway **可選**開關；預設與庫相同 |
| 設定來源 | `config/aicentral.yaml` + `secret.yaml` | **同一路徑**；Gateway 進程啟動時 `load_config()` |
| MCP | `mcp/` | v5.0 不暴露 HTTP；v5.1 可考慮 `POST /v1/mcp/...` |

---

## 設定（YAML）

延續 v4，**不**恢復根目錄 `.env` 作為主設定。Gateway 專用區塊併入 `config/aicentral.yaml`（可提交）與 `config/secret.yaml`（機密）：

```yaml
# config/aicentral.yaml（節錄）
gateway:
  enabled: true
  bind_host: 127.0.0.1          # 僅允許 127.0.0.1 或 ::1；寫其他值啟動失敗
  bind_port: 8080
  localhost_only: true          # v5.0 固定 true，不可關閉
  reject_non_local_client: true # middleware：client 非 127.0.0.1/::1 → 403
  max_body_bytes: 20971520
  max_image_bytes: 10485760
  allowed_image_mime: [image/jpeg, image/png, image/webp, image/gif]
  fetch_remote_images: false    # 預設不代抓 URL（防 SSRF）
  optional_token: null          # 預設 null = 不需 Authorization
  default_model: local-chat     # 文件用；HTTP 仍要求客戶端傳 model

# config/secret.yaml（v5.0 本機模式通常不需要 gateway 區塊）
# 若設定 optional_token，可寫：
# gateway:
#   optional_token: "dev-local-only"
```

| 設定 | 說明 |
|------|------|
| `bind_host` | **僅** loopback；實作應白名單校驗 |
| `reject_non_local_client` | 即使誤用反向代理，也拒絕 `X-Forwarded-For` 來自外網的請求（不信任轉發頭時只看 `request.client.host`） |
| `optional_token` | 非 `null` 時才要求 `Authorization: Bearer`；供本機多使用者共用一台機器時**可選** |
| `fetch_remote_images` | 預設 `false`；本機仍須防 SSRF（惡意腳本逼 Gateway 抓內網） |

---

## 本機安全（v5.0 簡化模型）

v5.0 **不**實作 [security.md](./security.md) 的 S1 Master Key / S2 限流；改以**網路隔離**為主、應用層為輔：

### 第一層：只 bind loopback（必要）

| 措施 | 行為 |
|------|------|
| 預設 `127.0.0.1:8080` | uvicorn / 啟動腳本**寫死**可覆寫 port，不可覆寫為 `0.0.0.0` |
| 設定檔防呆 | `bind_host: 192.168.x.x` → 啟動 **exit 1** |
| CLI 防呆 | `uvicorn ... --host 0.0.0.0` 若透過官方入口啟動應**忽略或拒絕** |

### 第二層：拒絕非本機客戶端（建議，可設定關閉）

| 措施 | 行為 |
|------|------|
| `reject_non_local_client: true` | `request.client.host` 不在 `127.0.0.1`、`::1` → **403** |
| 不信任 `X-Forwarded-For` | v5.0 不當 reverse proxy 使用，避免偽造來源 |

### 第三層：應用層（精簡）

| 措施 | 行為 |
|------|------|
| **不強制 Bearer** | 預設無 token；本機其他程序可直接呼叫 |
| **可選 token** | `optional_token` 設定後，未帶 Key → 401（防同一機器其他使用者誤用，非防外網） |
| **body / 圖片上限** | 防錯誤與惡意本機程序 |
| **不開 CORS** | 瀏覽器跨站不應直連 Gateway；若需網頁請走後端代理 |
| **日誌** | 不記錄 base64 圖全文；`optional_token` 不完整寫入 log |

### 明確排除的外部連線情境

| 情境 | v5.0 態度 |
|------|-----------|
| 區網另一台 PC 連 `http://192.168.x.x:8080` | **不支援**（未 listen 區網介面） |
| `bind 0.0.0.0` 方便手機調試 | **禁止**；請用 USB 埠轉發或改 import 函式庫 |
| Docker `-p 8080:8080` 對外 | 文件標註**僅** `-p 127.0.0.1:8080:8080` |
| frp / ngrok 暴露 | **不在支援範圍**；後果自負 |
| Windows 防火牆 | 建議阻擋入站 8080；縱使誤 bind 也有第二道 |

### 與 security.md 的關係

| 文件 | v5.0 |
|------|------|
| [security.md](./security.md) S1～S4 | **不套用**於預設本機 Gateway |
| 未來「對外模式」 | 另開規格：允許非 loopback + 強制 Master Key + S2 |

**驗收（本機安全）**：

- [ ] `bind_host` 非 loopback 時程序**無法啟動**
- [ ] `ss` / `netstat` 僅見 `127.0.0.1:8080`（或 `::1`），無 `0.0.0.0:8080`
- [ ] 從區網他機 `curl http://<本機區網IP>:8080` **連不上**
- [ ] `reject_non_local_client: true` 時，本機正常 `curl 127.0.0.1` 成功
- [ ] Ollama 仍建議只聽 `127.0.0.1:11434`

---

## 如何使用這個伺服器

### 1. 安裝

```powershell
cd aicentral
Copy-Item config\secret.yaml.example config\secret.yaml
# 編輯 config/secret.yaml：ollama.* 等；本機模式通常不需 gateway token
pip install -e ".[gateway]"
```

### 2. 啟動

```powershell
# 方式 A：模組入口（規劃）
python -m aicentral.gateway

# 方式 B：uvicorn（規劃；host 必須為 127.0.0.1）
uvicorn aicentral.gateway.app:app --host 127.0.0.1 --port 8080
```

啟動前確認 **Ollama**（或 yaml 指向的雲端）可用。  
啟動後請確認僅監聽 loopback（見上方本機安全驗收）。

### 3. 健康檢查

```bash
curl http://127.0.0.1:8080/health
# {"status":"ok","version":"0.5.0"}
```

### 4. 純文字對話

```bash
curl http://127.0.0.1:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "local-chat",
    "messages": [{"role": "user", "content": "你好"}]
  }'
```

> 若 `gateway.optional_token` 有設定，加上：`-H "Authorization: Bearer <optional_token>"`

### 5. 串流

```bash
curl http://127.0.0.1:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"local-chat","messages":[{"role":"user","content":"你好"}],"stream":true}' \
  --no-buffer
```

### 6. 文字 + 圖片（Base64）

```bash
# 將圖片轉 data URL 後放入 content 陣列（示意）
curl http://127.0.0.1:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d @request_with_image.json
```

`request_with_image.json` 範例：

```json
{
  "model": "cloud-chat",
  "messages": [
    {
      "role": "user",
      "content": [
        { "type": "text", "text": "描述這張圖" },
        { "type": "image_url", "image_url": { "url": "data:image/jpeg;base64,..." } }
      ]
    }
  ]
}
```

> 使用 **vision 模型**（yaml 別名指向支援圖片的 `model_id`）；否則 Gateway 回 400。

### 7. Python（OpenAI 官方 SDK）

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:8080/v1",
    api_key="not-needed",  # 本機預設無 token；SDK 仍需非空字串時可填任意占位
)
# 若有 optional_token：api_key="<optional_token>"

# 文字
r = client.chat.completions.create(
    model="local-chat",
    messages=[{"role": "user", "content": "你好"}],
)
print(r.choices[0].message.content)

# 串流
stream = client.chat.completions.create(
    model="local-chat",
    messages=[{"role": "user", "content": "你好"}],
    stream=True,
)
for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="", flush=True)
```

### 8. 其他語言 / 工具

任何能指定 **`base_url=http://127.0.0.1:8080/v1`** 的 OpenAI 相容客戶端均可使用；須在**同一台機器**上執行。  
**不必**安裝 `aicentral` Python 套件於客戶端。

### 9. Docker（可選，仍限本機）

```bash
# 僅映射到 host loopback，勿用 -p 8080:8080
docker compose -f docker/docker-compose.yml up gateway
# compose 內應為 ports: ["127.0.0.1:8080:8080"]
```

容器內 Gateway 仍只 listen `127.0.0.1`（或容器內 loopback + 上述 port 映射）。

### 10. 與「直接 import 函式庫」的選擇

| 情境 | 建議 |
|------|------|
| 同機 Python 應用（如 `aicentral-chat`） | `from aicentral import Chat` / `complete()`，**不經 HTTP** |
| 同機其他語言（Node、Go 等） | Gateway `http://127.0.0.1:8080` |
| 他機／手機／瀏覽器直連 | **不支援** v5.0；請在該機跑 consumer 或日後對外模式 |
| 本機腳本、測試 | 優先 import；需 HTTP 契約測試時才開 Gateway |

---

## 分階段交付

| 階段 | 內容 | 驗收 |
|------|------|------|
| **v5.0-alpha** | loopback bind + `POST` 純文字非串流 | `127.0.0.1` curl 可對話；區網 IP 連不上 |
| **v5.0-beta** | 串流 SSE | 終端機逐字輸出 |
| **v5.0** | 多模態 parts、body 上限、`reject_non_local_client` | vision 圖文；非本機 client → 403 |
| **v5.1** | `tools`、可選 MCP HTTP | 與 [mcp.md](./mcp.md) 對齊 |
| **v5.2** | `fetch_remote_images`（本機仍防 SSRF）；structured HTTP（可選） | — |
| **（未規劃）對外模式** | 非 loopback + [security.md](./security.md) S1/S2 | 獨立版本，非 v5.0 |

---

## 套件與部署產出

| 產出 | 說明 |
|------|------|
| `src/aicentral/gateway/` | FastAPI 應用與路由 |
| `pip install "aicentral[gateway]"` | 依賴：`fastapi`、`uvicorn[standard]`（見 `pyproject.toml`） |
| `python -m aicentral.gateway` | CLI 啟動（規劃） |
| `docker/` | 可選 Compose；**不**取代本機 `import` 開發流程 |
| `tests/gateway/` | 契約測試（OpenAI 請求/回應形狀、401、413、stream） |

---

## 測試策略

| 類型 | 內容 |
|------|------|
| **契約測試** | 固定 JSON fixture：文字 / 多模態 / 錯誤 400 |
| **整合測試** | TestClient + mock `complete()`；不強依真實 Ollama |
| **串流測試** | 解析 SSE `data:` 行直至 `[DONE]` |
| **本機隔離測試** | 非 loopback bind 啟動失敗、僅 `127.0.0.1:8080` 監聽、超大 body 413、可選 403 client IP |

---

## 驗收清單（v5.0 GA）

- [ ] OpenAI SDK 指向 `base_url` 可完成一輪文字對話
- [ ] `stream: true` 可逐 chunk 接收
- [ ] 含 `image_url`（base64）之請求在 vision 模型上成功
- [ ] 不支援 vision 的 model 回 **400** 且訊息可讀
- [ ] 僅監聽 `127.0.0.1`（或 `::1`），設定 `0.0.0.0` 無法啟動
- [ ] 區網他機無法連線至 Gateway port
- [ ] Gateway 僅委派 `core.complete()`，無重複 HTTP 實作於 routes
- [ ] 設定僅來自 `config/*.yaml`（與 v4 一致）
- [ ] 預設**不需** `Authorization`；`optional_token` 啟用時行為正確

---

## 與其他文件的關係

| 文件 | 關係 |
|------|------|
| [routing.md](./routing.md) | 庫內 Router ≠ Gateway；Gateway 消費同一 `model` 語意 |
| [security.md](./security.md) | 公網／對外模式參考；**v5.0 本機版不套用 S1/S2** |
| [mcp.md](./mcp.md) | MCP HTTP 暴露延後 v5.1 |
| [aicentral-v4.0.md](./aicentral-v4.0.md) | provider、yaml、fallback 為 v5 前置 |
| [concepts.md](./concepts.md) | `complete()` 語意不變；Gateway 為額外入口 |

---

## 小結

| 問題 | 答案 |
|------|------|
| 統一協定是什麼？ | **OpenAI Chat Completions**（JSON + 可選 SSE） |
| 圖片怎麼傳？ | `content` 陣列中的 `image_url`（建議 base64 data URL；遠端 URL 預設關閉） |
| 誰處理多供應商差異？ | 仍為 `providers/` + `transform/`；Gateway 只做 HTTP 殼 |
| 誰能連？ | **僅本機**（`127.0.0.1` / `::1`）；外部連線應失敗 |
| 需要 API Key 嗎？ | **預設不需要**；可選 `optional_token` |
| 怎麼用？ | `pip install "aicentral[gateway]"` → yaml → `curl http://127.0.0.1:8080/v1/chat/completions` |
| 與 `import aicentral` 關係？ | **並存**；同機 Python 優先 import，同機他語言走 Gateway |

實作順序建議：**loopback 強制 + 純文字 → 串流 → 多模態**；**勿**實作 `0.0.0.0` 或預設 Master Key。若未來要對外，另開「對外模式」並套用 [security.md](./security.md)。
