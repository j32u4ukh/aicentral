# aicentral v1.0 實作紀錄

> 規格：[aicentral.md](./aicentral.md) v1.0 章節  
> 狀態：**已實作**（函式庫本體；`aicentral-chat` 由消費方專案另行完成）

---

## 交付範圍

| 項目 | 狀態 |
|------|------|
| `complete(messages, model=...)` → `str` | ✅ |
| `providers/openai_compat.py` → Ollama OpenAI 相容 API | ✅ |
| 環境變數 `OLLAMA_*` | ✅ |
| 單元測試（mock HTTP） | ✅ |
| `aicentral-chat` 迴圈腳本 | ⏳ 獨立 repo，不在此次變更 |

---

## 目錄與檔案

```
src/aicentral/
├── __init__.py              # 匯出 complete、例外
├── client.py                # complete() 入口
├── exceptions.py            # AICentralError、ProviderError（v0.2 併入 core/errors）
└── providers/
    ├── __init__.py
    └── openai_compat.py     # POST /v1/chat/completions

tests/
├── test_version.py
└── test_complete.py         # mock httpx
```

較規劃多出的 `exceptions.py`：v1.0 需區分連線失敗與 HTTP 錯誤，暫放根目錄，v0.2 移至 `core/errors.py`。

---

## 請求流程（實作）

```
complete(messages, model?)
  → load_dotenv()（client 模組載入時）
  → 解析 OLLAMA_MODEL / 參數 model
  → providers.openai_compat.chat_completions(...)
  → httpx POST {base_url}/chat/completions
  → 解析 choices[0].message.content
```

---

## 參考 LiteLLM 的部分

| LiteLLM 概念 | 本專案對應 | 說明 |
|--------------|------------|------|
| `completion()` / `litellm.completion` | `complete()` | 統一函式入口，呼叫方只傳 `messages` + `model` |
| `litellm/llms/*` 供應商適配 | `providers/openai_compat.py` | 負責 HTTP 與請求/回應格式；v1.0 僅實作 OpenAI 相容這一支 |
| `model="provider/model"` 分派 | v1.0 省略 | 尚未有 `routing/`；預設 Ollama，model 為裸名如 `llama3.2` |
| OpenAI chat `endpoint = "chat/completions"` | `POST .../v1/chat/completions` | 與 `litellm/llms/openai/chat` 相同端點慣例 |
| `get_secret_str("OLLAMA_API_BASE")` 等 env | `OLLAMA_BASE_URL`、`OLLAMA_MODEL`、`OLLAMA_API_KEY` | 從環境讀取，不硬編碼金鑰 |
| `ProviderError` / HTTP 錯誤處理 | `exceptions.ProviderError` | 連線失敗、4xx/5xx、JSON 解析失敗 |
| `python-dotenv` 載入 | `client.py` 內 `load_dotenv()` | 對齊 LiteLLM 開發模式載入 `.env` |

**未採用（留待後續版本）**：

- LiteLLM Proxy / `master_key`、virtual keys → v0.5 `gateway/` + [security.md](./security.md)
- `litellm/llms/ollama/chat` 原生 Ollama API → v1.0 刻意改用 Ollama **OpenAI 相容** `/v1`，減少轉換程式碼
- Router、fallback、100+ providers → v0.2～v0.4
- 串流、`stream=True` → 未實作
- tiktoken、用量追蹤 → 未實作

---

## 參考 Instructor 的部分

| Instructor 概念 | v1.0 狀態 | 說明 |
|-----------------|-----------|------|
| `response_model` + Pydantic | ❌ 未實作 | 留 v0.3 `complete_structured()` |
| `from_provider("openai/...")` 統一入口 | 部分借鑒 | 僅借「單一 `complete` 入口」思想，尚無 provider 字串解析 |
| 驗證失敗重試 | ❌ | v0.3 `structured/validate.py` |
| Pydantic 依賴 | ❌ v1.0 未引入 | `pyproject.toml` 僅 `httpx` + `python-dotenv` |

v1.0 **本質上是 LiteLLM 的 completion 子集**，Instructor 能力在 v0.3 才合入。

---

## 環境變數

| 變數 | 預設 | 用途 |
|------|------|------|
| `OLLAMA_BASE_URL` | `http://localhost:11434/v1` | OpenAI 相容 API 根路徑 |
| `OLLAMA_MODEL` | `llama3.2` | `complete()` 未傳 `model` 時使用 |
| `OLLAMA_API_KEY` | `ollama` | `Authorization: Bearer`；本機通常可忽略 |

見根目錄 `.env.example`。

---

## 使用方式

```python
from aicentral import complete

reply = complete(
    messages=[{"role": "user", "content": "你好"}],
    model="llama3.2",  # 可省略，改用 OLLAMA_MODEL
)
print(reply)
```

前置：`ollama serve` 且 `ollama pull llama3.2`（或你設定的模型）。

```powershell
pip install -e ".[dev]"
pytest
```

---

## 測試策略

- **不**在 CI 依賴真實 Ollama（避免 flaky）。
- `tests/test_complete.py` 以 `unittest.mock` 攔截 `httpx.Client`，驗證：
  - 成功解析 `choices[0].message.content`
  - HTTP 4xx 拋出 `ProviderError`（含 `status_code`）
  - 連線失敗拋出 `ProviderError`
  - `complete()` 正確委派至 provider

整合測試可本機手動：`python -c "from aicentral import complete; print(complete([{'role':'user','content':'hi'}]))"`

---

## 已知限制（v1.0）

- 僅同步 `complete()`，無 `acomplete()`。
- 不支援串流回應。
- `messages` 為 `list[dict]`，尚無 `core/types.py` 型別。
- 僅支援 OpenAI 相容後端（Ollama）；雲端 OpenAI / Anthropic 見 v0.4。
- `load_dotenv()` 在 import `client` 時執行，可能與消費方自己的 dotenv 重複（可接受）。

---

## 下一步（v0.2）

- 抽出 `core/types.py`、`core/client.py`
- `routing/parser.py` 支援 `ollama/llama3.2`
- 將 `exceptions.py` 併入 `core/errors.py`
