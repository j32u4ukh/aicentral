# aicentral 專案架構

> 參考：[litellm.md](./litellm.md)、[instructor.md](./instructor.md)  
> 定位：輕量化合併 LiteLLM（統一呼叫）與 Instructor（結構化輸出）的設計思想，**不依賴** `litellm` / `instructor` 套件。

---

## 專案定位

**aicentral 是提供給其他專案使用的 AI 能力函式庫（library）**，不是承載業務的應用服務：

- ✅ 對外提供 `complete()` 等能力，由消費方 `import` 使用
- ✅ 可選的 HTTP Gateway（後續版本）
- ❌ 不在此 repo 封裝業務 API、領域 model、workflow
- ❌ 業務邏輯放在**消費方專案**（例如 [`aicentral-chat`](../../aicentral-chat)）

```
aicentral-chat / 你的後端
        │
        │  from aicentral import complete
        ▼
   aicentral（能力層）
        │
        ▼
   OpenAI / Anthropic / …
```

---

## 版本規劃總覽

| 版本 | 目標 | aicentral 產出 | 消費方範例 |
|------|------|----------------|------------|
| **v0.1**（第一版） | 能對話 | 一個 `complete()` + OpenAI provider | `aicentral-chat` 迴圈腳本 |
| **v0.2** | 好維護 | 拆出 `core/`、`routing/`、型別與錯誤 | 同上，可換 model 字串 |
| **v0.3** | 結構化輸出 | `complete_structured()` + `structured/` | 消費方定義 Pydantic model |
| **v0.4** | 多供應商 | 第二 provider、簡易 fallback | — |
| **v0.5** | 跨語言呼叫 | 可選 `gateway/` + Docker | 非 Python 客戶端 |

**原則**：每一版都可獨立跑通測試，不依賴上游 `litellm` / `instructor` 套件；只參考其設計與本機原始碼。

---

## v0.1 — 第一版（當前目標）

### 要做什麼

1. **aicentral**：實作 `complete(messages, model=...)`，能呼叫 OpenAI Chat Completions 並回傳助理文字。
2. **aicentral-chat**：一個終端機迴圈腳本，讀取使用者輸入 → 呼叫 `complete()` → 印出回覆。

### 驗收標準

```powershell
# aicentral repo
pip install -e ".[dev]"
pytest

# aicentral-chat repo（依賴可編輯安裝的 aicentral）
python chat.py
# 輸入「你好」→ 收到模型回覆
```

### v0.1 目錄結構（刻意極簡）

```
src/aicentral/
├── __init__.py          # 匯出 complete
├── client.py            # complete()：組裝請求、呼叫 provider、回傳 str
└── providers/
    └── openai.py        # httpx 呼叫 OpenAI API

tests/
└── test_complete.py     # mock HTTP 或整合測試（可選）
```

**v0.1 刻意不做**：

| 模組 / 設施 | 原因 |
|-------------|------|
| `routing/` | model 先在 `client.py` 內解析 `openai/...` 或寫死預設值 |
| `structured/` | 對話範例不需要 `response_model` |
| `gateway/`、`docker/` | 本地 Python 呼叫即可 |
| `config/`（Pydantic Settings） | `.env` + `os.getenv` 足夠 |
| `core/types.py`、`errors.py` | v0.2 再抽離 |

### v0.1 對外 API

```python
from aicentral import complete

reply = complete(
    messages=[
        {"role": "user", "content": "你好"},
    ],
    model="openai/gpt-4o-mini",  # 或簡化為只接受 "gpt-4o-mini"
)
print(reply)  # str
```

實作可為同步；若用 `httpx` 非同步，提供 `acomplete()` 亦可，但 v0.1 二擇一即可。

### v0.1 依賴（`pyproject.toml`）

| 套件 | 用途 |
|------|------|
| `httpx` | 呼叫 OpenAI API |
| `python-dotenv` | 載入 `OPENAI_API_KEY` |

`pydantic` / `pydantic-settings` 留到 v0.3（結構化輸出）再引入。

### aicentral-chat（v0.1 消費方）

與 aicentral 分 repo，職責僅為**示範如何引用函式庫**：

```
aicentral-chat/
├── pyproject.toml       # 依賴 ../aicentral（path / editable）
├── .env.example         # OPENAI_API_KEY=
├── chat.py              # while True: input → complete → print
└── docs/README.md
```

**禁止**在 aicentral-chat 內直接 `httpx` 打 OpenAI；一律經 `aicentral.complete()`。

### v0.1 請求流程

```
complete(messages, model)
  → client 解析 model（v0.1：僅 openai）
  → providers.openai.chat(...)
  → 回傳 message.content 字串
```

---

## v0.2 — 模組化與路由

在 v0.1 跑通後重構，對齊長期架構的「骨架」，仍只有 `complete()`：

```
src/aicentral/
├── __init__.py
├── core/
│   ├── types.py         # Message、ChatResponse
│   ├── errors.py        # ProviderError 等
│   └── client.py        # complete() 入口
├── providers/
│   ├── base.py
│   ├── registry.py
│   └── openai.py
└── routing/
    └── parser.py        # "openai/gpt-4o-mini" → (provider, model_id)
```

| 產出 | 說明 |
|------|------|
| 型別化 messages | 不再只用 `list[dict]` |
| `routing/parser` | 統一 model 字串格式 |
| 測試分目錄 | `tests/providers/`、`tests/routing/` |

---

## v0.3 — 結構化輸出（Instructor-lite）

| 產出 | 說明 |
|------|------|
| `structured/` | schema 產生、extract、validate、重試 |
| `complete_structured(response_model=...)` | 回傳 Pydantic 實例 |
| 依賴加入 `pydantic` | 設定可選 `pydantic-settings` |

流程：

```
complete_structured(response_model=User)
  → structured.schema.build(User)
  → complete(..., tools=...)      # 仍走同一條 provider 路徑
  → structured.extract / validate
  → User 實例（失敗則重試，次數可設定）
```

消費方（非 aicentral repo）定義領域 model，例如：

```python
class Ticket(BaseModel):
    title: str
    priority: int

ticket = complete_structured(messages=[...], response_model=Ticket, model="...")
```

---

## v0.4 — 多供應商與 fallback

| 產出 | 說明 |
|------|------|
| `providers/anthropic.py`（或第二家） | 與 OpenAI 並存 |
| `routing/router.py` | 設定檔驅動的簡易 fallback 鏈 |
| `config/` | 模型別名、預設 model（yaml / env） |

仍不實作 100+ provider、adaptive router、Admin UI。

---

## v0.5 — 可選 HTTP Gateway

| 產出 | 說明 |
|------|------|
| `gateway/` | FastAPI、`POST /v1/chat/completions` |
| `pip install "aicentral[gateway]"` | 可選依賴 |
| `docker/` | 容器化部署（可選） |

Gateway **只委派** `core.complete()`，不重寫 completion 邏輯。  
不包含 DB、用量報表、guardrails（除非日後另開版本）。

---

## 目標架構（v0.2 之後逐步長成）

完整形態供對照，**不必在 v0.1 一次建立**：

```
                    ┌─────────────────────────────────────┐
  其他專案 / CLI     │  gateway（v0.5，可選）               │
                    └──────────────┬──────────────────────┘
                                   │
                    ┌──────────────▼──────────────────────┐
                    │  core — complete / complete_structured │
                    └──────────────┬──────────────────────┘
                                   │
         ┌─────────────────────────┼─────────────────────────┐
         │                         │                         │
  ┌──────▼──────┐          ┌───────▼───────┐         ┌───────▼───────┐
  │ providers   │          │ routing       │         │ structured    │
  │ v0.1 起     │          │ v0.2 起       │         │ v0.3 起       │
  └─────────────┘          └───────────────┘         └───────────────┘
```

**依賴方向**：`gateway` → `core` → `providers` / `routing` / `structured`  
**禁止**：`providers` 依賴 `structured`。

---

## 與上游概念的對照

| 上游 | aicentral 模組 | 最早版本 |
|------|----------------|----------|
| LiteLLM `completion()` | `complete()` | v0.1 |
| LiteLLM `llms/*` | `providers/*` | v0.1 |
| LiteLLM `router_strategy/*` | `routing/*` | v0.2 |
| Instructor `response_model` | `complete_structured()` + `structured/*` | v0.3 |
| LiteLLM `proxy/*` | `gateway/*` | v0.5 |
| 業務 / 對話 UI | **消費方**（`aicentral-chat` 等） | v0.1 起 |

---

## 倉庫內可延後的腳手架

以下存在於 repo 但**不阻擋 v0.1**，實作 `complete()` 前可忽略：

- `docker/` — v0.5 再用
- `scripts/` — 輔助安裝與 `.env`，保留即可
- `docs/litellm.md`、`instructor.md` — 設計參考，非執行必要

---

## 小結

| 問題 | 答案 |
|------|------|
| 第一版要做什麼？ | **`complete()`** + **`aicentral-chat` 迴圈腳本** |
| 第一版目錄要多大？ | **`client.py` + `providers/openai.py`** 即可 |
| 完整架構何時做？ | **v0.2～v0.5 漸進**，見上方版本表 |
| 業務放哪？ | **消費方專案**，不在 aicentral |

實作 v0.1 時，以「能從終端機完成一輪對話」為唯一驗收；通過後再按版本表擴充模組。
