# Proxy（本機 HTTP Gateway）

> 完整規格：[aicentral-v5.0 .md](./aicentral-v5.0%20.md) · 庫內選路（非 HTTP）：[routing.md](./routing.md) · 設定：`../config/aicentral.yaml`

---

## 一句話

**Proxy** 是 aicentral 的**可選本機 HTTP 服務**（程式目錄 `src/aicentral/gateway/`）：把 **OpenAI Chat Completions** 格式的 HTTP 請求轉成對 **`core.complete()`** 的呼叫，讓**同一台電腦**上的其他程式（Node、Go、curl、OpenAI SDK 等）不必 `import aicentral` 也能使用同一套模型與 yaml 設定。

**不是** LiteLLM 那種對區網／公網開放的 Proxy；v5.0 **只聽** `127.0.0.1`（或 `::1`）。

---

## 在架構中的角色

```
┌──────────────────────────────────────────────────────────┐
│  本機（同一台機器）                                        │
│                                                          │
│  你的 App / 腳本 / OpenAI SDK                             │
│       │  HTTP（OpenAI 格式）                              │
│       ▼                                                  │
│  ┌─────────────┐     ┌──────────────┐     ┌───────────┐ │
│  │ Proxy       │ ──► │ core +       │ ──► │ Ollama /  │ │
│  │ :8080       │     │ routing      │     │ 雲端 API  │ │
│  │ (gateway/)  │     │ complete()   │     │           │ │
│  └─────────────┘     └──────────────┘     └───────────┘ │
│                                                          │
│  同機 Python 專案也可略過 Proxy，直接 import aicentral      │
└──────────────────────────────────────────────────────────┘
```

| 層級 | 做什麼 | 不做什麼 |
|------|--------|----------|
| **Proxy（HTTP）** | 驗證本機連線、解析 JSON/SSE、轉成內部 `messages` | 不實作 LLM 連線邏輯、不取代 Router |
| **Router（庫內）** | 依 `model` 選 provider、金鑰、fallback | 不是 HTTP 接口，見 [routing.md](./routing.md) |
| **providers/** | 對 Ollama / OpenAI / Claude / Gemini 發 HTTP | 不知道誰是「外部客戶端」 |

Proxy **只委派** `complete()`；業務邏輯、對話狀態、MCP 編排仍應在**消費方專案**完成。

---

## 與其他呼叫方式的差別

| 方式 | 適用情境 |
|------|----------|
| `from aicentral import complete, Chat` | 同機 **Python**；延遲最低、最簡單（如 [aicentral-chat](../../aicentral-chat)） |
| **Proxy HTTP** | 同機 **非 Python**、或想用現成 **OpenAI SDK** / Postman |
| 直接打 Ollama `:11434` | 繞過 aicentral 路由與 yaml；不建議若已用 aicentral 統一設定 |

| 名稱 | 易混淆處 |
|------|----------|
| **aicentral Proxy** | 本文件；本機 `gateway/`，OpenAI 相容 |
| **LiteLLM Proxy** | 上游專案；對外 Gateway、虛擬金鑰等，見 [litellm.md](./litellm.md) |
| **routing（Router）** | 函式庫內部選 model，**沒有** HTTP port |

---

## 對外接口（摘要）

| 方法 | 路徑 | 說明 |
|------|------|------|
| `GET` | `/health` | 健康檢查 |
| `POST` | `/v1/chat/completions` | 對話（支援 `stream: true` SSE） |

請求體對齊 OpenAI：`model`（必填）、`messages`、`stream` 等。  
`messages[].content` 可為字串，或 **parts**（`text`、`image_url`；圖片建議 base64 data URL）。

回應亦為 OpenAI 形狀（非串流 `chat.completion`，串流 `chat.completion.chunk` + `data: [DONE]`）。

---

## 安裝與啟動

### 前置

1. 已設定 `config/secret.yaml`（可由 `config/secret.yaml.example` 複製）
2. 本機 LLM 可用（例如 Ollama 已啟動且已 pull 模型）

### 安裝

```powershell
cd aicentral
pip install -e ".[gateway]"
```

### 啟動 Proxy

```powershell
python -m aicentral.gateway
```

或：

```powershell
uvicorn aicentral.gateway.app:app --host 127.0.0.1 --port 8080
```

預設位址：**`http://127.0.0.1:8080`**（port 可在 `config/aicentral.yaml` 的 `gateway.bind_port` 修改）。

啟動後請確認僅監聽 loopback（例如 `netstat` 只見 `127.0.0.1:8080`）。

---

## 使用範例

### 健康檢查

```bash
curl http://127.0.0.1:8080/health
```

### 文字對話

```bash
curl http://127.0.0.1:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d "{\"model\":\"local-chat\",\"messages\":[{\"role\":\"user\",\"content\":\"你好\"}]}"
```

`local-chat` 等名稱來自 `config/aicentral.yaml` 的 `model_list` 別名；也可用 `ollama/gemma4:e2b` 這類 provider 字串。

### 串流

```bash
curl http://127.0.0.1:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d "{\"model\":\"local-chat\",\"messages\":[{\"role\":\"user\",\"content\":\"你好\"}],\"stream\":true}" \
  --no-buffer
```

### Python（OpenAI 官方 SDK）

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:8080/v1",
    api_key="not-needed",  # 預設不需金鑰；見下方設定
)

response = client.chat.completions.create(
    model="local-chat",
    messages=[{"role": "user", "content": "你好"}],
)
print(response.choices[0].message.content)
```

其他語言只要支援「自訂 OpenAI base URL」的客戶端，皆可指向 `http://127.0.0.1:8080/v1`，且程式須跑在**同一台機器**上。

---

## 設定

Proxy 行為由 **`config/aicentral.yaml`** 的 `gateway:` 區塊控制（與 `model_list`、路由共用同一份設定）：

```yaml
gateway:
  enabled: true
  bind_host: 127.0.0.1
  bind_port: 8080
  reject_non_local_client: true
  optional_token: null   # 非 null 時須帶 Authorization: Bearer <token>
```

機密可選寫在 **`config/secret.yaml`**：

```yaml
gateway:
  optional_token: "dev-local-only"
```

| 設定 | 說明 |
|------|------|
| `bind_host` | 僅允許 `127.0.0.1` / `::1` |
| `reject_non_local_client` | 拒絕非本機來源的 HTTP 請求（403） |
| `optional_token` | 本機可選簡單 Bearer；**非**對外 Master Key 方案 |

模型、金鑰、fallback 仍由 **`model_list`**、`secret.yaml` 的 `ollama` / `openai` 等決定，與直接 `import aicentral` 時相同。

---

## 安全與範圍（v5.0）

| 項目 | 說明 |
|------|------|
| **僅 localhost** | 不支援 `0.0.0.0`、不給區網／公網用 |
| **預設免 API Key** | 依賴「只聽本機」隔離；可選 `optional_token` |
| **不開 CORS** | 瀏覽器前端請改走自家後端，不要直連 Proxy |
| **日後對外** | 需另開模式並參考 [security.md](./security.md) |

---

## 常見問題

| 問題 | 說明 |
|------|------|
| Proxy 和 Router 差在哪？ | Router 在 process 內選路；Proxy 是 **HTTP 殼**，再呼叫 `complete()` |
| 為什麼還要 Proxy，不能都用 import？ | 非 Python、或想用 OpenAI SDK 時，HTTP 較省事 |
| 他機連不上？ | 預期行為；v5.0 不支援遠端連線 |
| 要 Docker 嗎？ | v5.0 **不需要**；`pip install` + 本機啟動即可 |
| 錯誤 400 缺 model？ | HTTP 請求必須帶 `model`，Proxy 不會自動填預設 |

---

## 延伸閱讀

| 文件 | 內容 |
|------|------|
| [aicentral-v5.0 .md](./aicentral-v5.0%20.md) | API 細節、多模態、錯誤碼、分階段交付 |
| [routing.md](./routing.md) | `model` 字串、yaml 別名、fallback |
| [concepts.md](./concepts.md) | `complete()`、`Chat` 語意 |
| [security.md](./security.md) | 未來若對外暴露時的安全規劃 |
