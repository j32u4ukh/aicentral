# aicentral v3.0 — 結構化輸出（Instructor-lite）

> 規格基線：[aicentral.md](./aicentral.md) · 設計參考：[instructor.md](./instructor.md) · 上一版：[aicentral-v2.0.md](./aicentral-v2.0.md)  
> 狀態：**規劃中**（目標函式庫 **v0.4.0**）

---

## 一句話

v3.0 在既有 `complete()` / `Chat` 之上新增 **`complete_structured(response_model=...)`**，由消費方定義 Pydantic model，aicentral 負責 **schema 產生、呼叫模型、解析、驗證與可設定重試**；**不安裝** `instructor` 套件。

> **重要**：截至函式庫 **v0.3.0**，結構化輸出**尚未實作**；本文件描述的是 **v3.0 規劃**（目標 **v0.4.0**）。下方「現況 vs 規劃」一節對照目前程式與本規格之差異。

---

## 現況（v0.3.0）vs v3.0 規劃

### 目前程式庫有什麼

| 項目 | v0.3.0（現在） | v3.0 規劃（v0.4.0） |
|------|----------------|---------------------|
| `complete_structured()` | ❌ 不存在 | ✅ P0 |
| `structured/` 目錄 | ❌ 不存在 | ✅ `schema` / `extract` / `validate` |
| `Chat.complete_structured()` | ❌ 不存在 | ✅ P1 |
| `pydantic` 依賴 | ❌ 僅 `httpx`、`python-dotenv` | ✅ 必要依賴 |
| `StructuredOutputError` | ❌ 不存在 | ✅ P0 |
| `__init__.py` 匯出 | `complete`、`Chat`、`parse_model`… | + `complete_structured` |
| 主 API 回傳 | `str` 或 `Iterator[str]` | + Pydantic 實例 |
| Provider 回傳 | 只解析 `message.content` → `str` | 需 **raw** 回應（含 `tool_calls`） |
| 驗證 / 重試 | 無 | Pydantic validate + `max_retries` |
| 結構化串流 | 無（亦無 API） | v3.0 **刻意不做**（見下方專節） |

**一句話**：現在只有「跟模型說話拿字串」；v3.0 要在函式庫內建 **schema → tool call → extract → validate → 重試** 整條管線。

### 文件與程式的落差

| 來源 | 寫了什麼 | 實際 |
|------|----------|------|
| `README.md` / `pyproject.toml` description | 提到 structured outputs、`complete_structured()` | **產品方向**，v0.3.0 尚未實作 |
| [concepts.md](./concepts.md) | `complete_structured()` **規劃中** | 與程式一致 |
| 本文件 | 狀態：**規劃中** | 與程式一致 |

實作 v3.0 後應同步：將本文件改為「已實作」、更新 `__version__` 為 **0.4.0**、README 範例改為可執行程式碼。

### 現階段消費方能做什麼（繞路，非結構化 API）

```python
from aicentral import complete

raw = complete(
    messages=[{"role": "user", "content": "請用 JSON 回傳 title 和 priority"}],
    model="ollama/gemma4:e2b",
)
# raw 是 str → 消費方自行 json.loads、自行驗證、自行重試
```

理論上 `complete(..., tools=[...])` 可把 `tools` 經 `**kwargs` 併入 provider payload，但：

- 沒有從 Pydantic 產生 schema 的 helper
- `chat_completions` **只回傳 content 字串**，無法讀 `tool_calls`
- 沒有 `response_model` 型別與 `StructuredOutputError`

因此**不視為** aicentral 已提供結構化輸出。

### v3.0 規劃後的用法（對照）

```python
from pydantic import BaseModel
from aicentral import complete_structured  # v3.0 起


class Ticket(BaseModel):
    title: str
    priority: int


ticket = complete_structured(
    messages=[{"role": "user", "content": "伺服器當機，很急"}],
    response_model=Ticket,
)
# ticket 為驗證過的 Ticket 實例（規劃行為）
```

---

## 定位與邊界

| 層級 | 職責 |
|------|------|
| **消費方專案** | 定義領域 `BaseModel`（例如 `Ticket`、`UserProfile`） |
| **aicentral `structured/`** | 從 model 產生 tool schema、從回應抽取 JSON、Pydantic 驗證、重試迴圈 |
| **aicentral `core` + `providers`** | 仍負責 HTTP；`complete_structured` **委派** `complete()`，不複製連線邏輯 |
| **aicentral `routing`** | `model="ollama/gemma4:e2b"` 等字串解析（v2.0 已有） |

**不做的事（維持 v1.x～v2.x 原則）**：

- 不在 aicentral repo 放業務 model 或 workflow
- 不引入 `instructor` / `litellm` 依賴
- 不實作 Instructor 的 `Partial`、`IterableModel`、batch、cache 等進階 DSL（可列 v3.1+）
- 不強制改寫 `aicentral-chat`（對話範例仍以自由文字 `complete` 為主）

**與 `complete()` 的關係**：

| | `complete()` | `complete_structured()` |
|--|--------------|-------------------------|
| 回傳 | `str` 或 `Iterator[str]`（`stream=True`） | **單一** Pydantic 實例（v3.0 **刻意不實作**結構化串流，見下方專節） |
| 典型用途 | 聊天、摘要、開放問答 | 抽取、分類、表單欄位、API 契約輸出 |
| 底層 HTTP | `providers/*` | **同一條**；多傳 `tools` / `tool_choice`（或 fallback 策略） |

**與 `Chat` 的關係（v3.0 規劃）**：

| 項目 | 決策 |
|------|------|
| `Chat.complete_structured(prompt, response_model=...)` | **P1**：內部組 `messages` 後呼叫 `complete_structured`；有狀態時成功後寫入歷史（與文字 `complete` 相同時機） |
| `Chat.complete(..., stream=True)` + 結構化 | v3.0 **不提供**；聊天用 `complete(stream=True)`，抽取用 `complete_structured` |
| 無狀態 `Chat` + `response_model` | 支援，與 v1.1 `context=` 語意一致 |

---

## 結構化與串流：刻意不做，還是技術上不能做？

**結論（v3.0）**：屬於**範圍決策（刻意不做）**，不是「永遠不能做」。v0.3.0 是連結構化 API 都還沒有，更談不上結構化串流。

| 問題 | 答案 |
|------|------|
| v0.3.0 有結構化串流嗎？ | **沒有**——因為沒有 `complete_structured` |
| v3.0 會做結構化串流嗎？ | **不會**——列在「不在 v3.0 範圍」，延後 v3.1+ |
| 技術上未來能做嗎？ | **可以**，但需另訂 API（例如 Instructor 的 `Partial[T]`、串流累積 JSON 再增量 validate） |

### 為何 v3.0 刻意不做結構化串流

1. **驗證時點**：Pydantic `model_validate` 需要**完整** JSON；tool `arguments` 在串流中常分段抵達，須等全文或做增量解析，複雜度明顯高於「收齊再驗證一次」。
2. **主路徑是 tool_calls**：v3.0 P0 假設模型一次回傳完整 `function.arguments`；與「邊收邊顯示欄位」的 UX 不同。
3. **與 `complete(stream=True)` 分工**：終端聊天、長文生成繼續用既有串流；結構化用於抽取、分類、API 契約，多為**短回覆、一次拿結果**。
4. **控制範圍**：v3.0 先交付可用的 `complete_structured() -> T`；進階 DSL（`Partial[T]`、Iterable model）對齊 Instructor 的 `dsl/`，列 **v3.1+**。

### 消費方該怎麼選（v3.0 起仍適用）

| 需求 | 建議 API |
|------|----------|
| 終端機邊打邊看、長文助理回覆 | `complete(..., stream=True)` 或 `Chat.complete(..., stream=True)` |
| 從使用者輸入抽出固定欄位、回傳給後端 API | `complete_structured(..., response_model=...)` |
| 既要串流又要結構化欄位 | v3.0：**拆兩次呼叫**或 v3.0 前自行 parse；v3.1+ 再評估 `Partial` / 串流結構化 |

### 未來若要做（v3.1+ 草案，非 v3.0 承諾）

- `complete_structured(..., stream=True) -> Iterator[Partial[T]]` 或類似型別
- 串流 SSE 累積 `tool_calls[].function.arguments`，達可 parse 片段時 yield 部分欄位
- `Chat` 是否跟進：待 API 穩定後再定

**API 設計原則**：`complete_structured` **不提供** `stream` 參數，與 `complete` 的 overload 分離，避免呼叫方誤以為能 `stream=True` 卻拿到 `Ticket` 實例。

---

## 交付範圍

| 項目 | 優先 | 說明 |
|------|------|------|
| `structured/schema.py` — `build_tool(response_model)` | P0 | 由 Pydantic v2 model 產生 OpenAI `tools[]` 單一 function schema |
| `structured/extract.py` — 從回應取 JSON | P0 | 優先 `tool_calls`；可選 fallback 解析 `message.content` 內 JSON |
| `structured/validate.py` — `model_validate` + 錯誤訊息 | P0 | 驗證失敗拋出可重試用的例外 |
| `core/client.py` — `complete_structured()` | P0 | 入口：組 messages、重試迴圈、回傳實例 |
| 依賴 `pydantic>=2` | P0 | 必要；消費方通常已安裝 |
| 單元測試（mock HTTP / 假 tool 回應） | P0 | 不依賴本機 Ollama |
| `StructuredOutputError`（或細分例外） | P0 | 區分「模型沒照格式」與「Provider 連線錯誤」 |
| 環境變數 `AICENTRAL_STRUCTURED_MAX_RETRIES` | P1 | 預設 2（即最多 3 次嘗試） |
| 重試時附加驗證錯誤到 user 訊息 | P1 | 參考 Instructor：把 Pydantic 錯誤餵回模型修正 |
| `Chat.complete_structured()` | P1 | 有/無狀態皆可用 |
| `from aicentral import complete_structured` | P0 | `__init__.py` 匯出 |
| JSON-in-content fallback（無 tool_calls） | P2 | 相容較舊或不穩定的本機模型 |
| `pydantic-settings` + `config/` | P2 | 仍可用 `.env` + `os.getenv` 滿足 v3.0 |
| `acomplete_structured` 非同步 | — | v3.1+ 或與 v1.2 `acomplete` 一併 |
| 結構化 + `stream=True` | — | **刻意不做**（範圍外，非遺漏）；見「結構化與串流」 |
| 多 function / 多 schema 擇一 | — | v3.0 僅 **單一** `response_model` |
| HTTP Gateway 暴露 structured | — | v5.0 |

---

## 目錄結構（規劃）

```
src/aicentral/
├── __init__.py                 # + complete_structured, StructuredOutputError
├── core/
│   └── client.py               # complete() 既有；+ complete_structured()
├── structured/                 # v3.0 新增
│   ├── __init__.py
│   ├── schema.py               # Pydantic → OpenAI tool definition
│   ├── extract.py              # choices[0].message → dict
│   ├── validate.py             # dict → BaseModel 實例
│   └── retry.py                # 重試迴圈與錯誤訊息組裝（可併入 client）
├── providers/                  # 不 import structured
├── routing/
└── chat.py                     # P1: complete_structured 包裝

tests/
├── structured/
│   ├── test_schema.py
│   ├── test_extract.py
│   ├── test_validate.py
│   └── test_retry.py
└── test_complete_structured.py # 整合 mock provider
```

**依賴方向**（與 [aicentral.md](./aicentral.md) 一致）：

```
complete_structured  →  structured/*  →  pydantic
                    →  complete()  →  routing  →  providers
```

**禁止**：`providers/*` import `structured/*`。

---

## 對外 API

### 模組級（主入口）

```python
from pydantic import BaseModel, Field
from aicentral import complete_structured


class Ticket(BaseModel):
    title: str = Field(description="工單標題")
    priority: int = Field(ge=1, le=5, description="1 最低、5 最高")


ticket = complete_structured(
    messages=[{"role": "user", "content": "伺服器當機，很急"}],
    response_model=Ticket,
    model="ollama/gemma4:e2b",  # 可省略，走 OLLAMA_MODEL + parse_model
    max_retries=2,              # 可選；預設讀環境變數
)
assert isinstance(ticket, Ticket)
```

### `Chat`（P1）

```python
from aicentral import Chat

chat = Chat(model="ollama/gemma4:e2b")
ticket = chat.complete_structured(
    "請從上一句建立工單",
    response_model=Ticket,
)
```

### 簽名草案

```python
def complete_structured[T: BaseModel](
    messages: list[Message],
    response_model: type[T],
    model: str | None = None,
    *,
    max_retries: int | None = None,
    system: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    mode: Literal["tool", "json"] = "tool",  # P2: json fallback
    **kwargs: Any,
) -> T: ...
```

- **不**提供 `stream` 參數——v3.0 **刻意不實作**結構化串流（見「結構化與串流」），不是暫時漏做。
- `**kwargs` 透傳至 `complete()` / provider（例如 `temperature`），但 **`tools` / `tool_choice` 由 structured 層管理**，消費方不應覆寫；亦不得透過 `kwargs` 傳 `stream=True` 混入結構化路徑（實作時應忽略或拒絕）。

---

## 請求流程

### 主路徑（tool calling，P0）

```
complete_structured(messages, response_model=Ticket, model=...)
  → parse_model(model) → (provider, model_id)
  → structured.schema.build_tool(Ticket)
       → tools=[{ "type": "function", "function": { "name", "description", "parameters" } }]
       → tool_choice 鎖定該 function（OpenAI 相容：name 或 required tool）
  → 迴圈 attempt = 0 .. max_retries:
       → complete(
            messages=messages + [可選：上一輪驗證錯誤修正提示],
            model=...,
            tools=...,
            tool_choice=...,
          )
       → structured.extract(raw_response) → dict | None
       → structured.validate(dict, Ticket) → Ticket 實例
       → 成功則 return
  → 用盡重試 → raise StructuredOutputError
```

`complete()` 內部仍為：

```
parse_model → get_provider_module → openai.chat_completions(..., **extra)
```

v2.0 的 `openai._build_request` 已支援 `**extra` 併入 payload，**v3.0 不必新增 provider 檔案**，僅需確保 `chat_completions` 回傳足夠資訊供 `extract`（見下方「Provider 回傳契約」）。

### Fallback（JSON in content，P2）

當模型不穩定支援 `tool_calls` 時：

```
mode="json"
  → system 追加「僅回傳符合 schema 的 JSON，不要 markdown」
  → complete(..., response_format={"type": "json_object"})  # 若端點支援
  → extract 改從 message.content  strip + json.loads
  → validate → Ticket
```

P0 驗收以 **mock 的 tool_calls 路徑** 為準；本機 Ollama 實測列為手動驗收（見下方）。

---

## `structured/` 模組職責

| 模組 | 輸入 | 輸出 | 備註 |
|------|------|------|------|
| `schema.build_tool(model)` | `type[BaseModel]` | `tools`, `tool_choice`, `tool_name` | 使用 `model.model_json_schema()`；function `name` 預設 snake_case 類名（如 `ticket`） |
| `extract.from_chat_completion(data)` | provider 回傳的 `dict` 或封裝 | `dict[str, Any] \| None` | 先讀 `choices[0].message.tool_calls[0].function.arguments`（JSON 字串） |
| `validate.parse(data, model)` | `dict`, `type[T]` | `T` | `model.model_validate(data)`；`ValidationError` 轉成可讀字串供重試 |
| `retry.run(...)` | callable + `max_retries` | `T` | 可選獨立檔，或寫在 `core/client` |

### Schema 產生要點

- 使用 **Pydantic v2** `model_json_schema()`，必要時 `model_config` / `Field(description=...)` 改善模型填寫品質。
- 單一 function：`name` 建議為類名小寫（`Ticket` → `ticket`），與 `tool_choice` 一致。
- **不在 aicentral 內建領域 model**；僅處理消費方傳入的 class。

### Extract 要點

優先順序：

1. `message.tool_calls[0].function.arguments`（JSON 字串 → `dict`）
2. （P2）`message.content` 中 JSON 區塊 / 整段 `json.loads`
3. 皆失敗 → 本輪視為「未產出」，進入重試或最終 `StructuredOutputError`

### 重試要點

| 情境 | 是否重試 |
|------|----------|
| Pydantic `ValidationError` | 是（附錯誤摘要到新 user 訊息） |
| 無 `tool_calls` / 空 arguments | 是 |
| `ProviderError`（HTTP 4xx/5xx、連線失敗） | **否**（直接拋出，避免掩蓋基礎設施問題） |
| 超過 `max_retries` | 拋 `StructuredOutputError`，可帶 `last_error` / `attempts` |

重試時建議追加的 user 訊息（示意）：

```text
上一輪輸出未通過驗證，請修正後僅呼叫工具 function。
錯誤：priority: Input should be less than or equal to 5
```

---

## Provider 回傳契約（v3.0 對 `openai.py` 的小幅調整）

目前 `chat_completions` 只回傳 `str`（`content`）。結構化需要 **完整 choice**，建議二擇一（實作時擇優）：

| 方案 | 作法 | 優點 |
|------|------|------|
| A | `chat_completions` 增加 `return_raw: bool`，True 時回傳 `dict` | 改動小 |
| B | 新增 `chat_completions_raw(...) -> dict`，`chat_completions` 仍只回 str | 職責清晰 |

`complete_structured` 只呼叫 **raw** 路徑；一般 `complete()` 行為不變。

Extract 假設的 JSON 形狀（OpenAI 相容）：

```json
{
  "choices": [{
    "message": {
      "role": "assistant",
      "tool_calls": [{
        "function": {
          "name": "ticket",
          "arguments": "{\"title\": \"...\", \"priority\": 3}"
        }
      }]
    }
  }]
}
```

---

## 例外與錯誤

| 例外 | 繼承 | 時機 |
|------|------|------|
| `ProviderError` | 既有 | HTTP / 連線 / 非預期回應格式（v2.0） |
| `StructuredOutputError` | 建議 `ProviderError` 或獨立 `AICentralError` | 重試用盡仍無法得到合法 `response_model` |

`StructuredOutputError` 建議屬性：

- `response_model: type[BaseModel]`
- `attempts: int`
- `last_validation_error: str | None`

---

## 環境變數

| 變數 | 預設 | 說明 |
|------|------|------|
| `OLLAMA_MODEL` | `gemma4:e2b` | 與 v2.0 相同；`model=None` 時使用 |
| `AICENTRAL_STRUCTURED_MAX_RETRIES` | `2` | 驗證失敗後額外重試次數 |
| `AICENTRAL_STRUCTURED_MODE` | `tool` | （P2）`tool` \| `json` |

既有 `AICENTRAL_SYSTEM_PROMPT` 仍會經 `_with_system_prompt` 插入；結構化可在 system 加一句「輸出必須符合指定工具 schema」（實作時評估是否與繁中提示衝突）。

---

## 依賴（`pyproject.toml`）

| 套件 | 版本 | 用途 |
|------|------|------|
| `pydantic` | `>=2.0` | schema、驗證、`response_model` 型別 |
| `httpx` | 既有 | 不變 |
| `python-dotenv` | 既有 | 不變 |
| `pydantic-settings` | 可選 P2 | 集中設定；v3.0 可用 env 代替 |

```toml
dependencies = [
    "httpx>=0.27.0",
    "python-dotenv>=1.0.0",
    "pydantic>=2.0.0",
]
```

---

## 測試計畫

| 測試檔 | 內容 |
|--------|------|
| `test_schema.py` | 簡單 model → `tools[0].function.parameters` 含必填欄位 |
| `test_extract.py` | 假 `tool_calls`、壞 JSON、缺欄位 |
| `test_validate.py` | 合法/非法 dict → `Ticket` / `ValidationError` |
| `test_complete_structured.py` | `@patch` provider raw 回應；第一次壞資料、第二次成功 |
| `test_chat_structured.py`（P1） | `Chat.complete_structured` 有狀態寫入歷史 |

**不要求** CI 連本機 Ollama；手動驗收腳本可放在 `scripts/` 或 `tests/integration/`（標記 optional）。

---

## 驗收標準

```powershell
# 1. 單元測試
cd aicentral
pip install -e ".[dev]"
pytest

# 2. 消費方腳本（示意，可放在 tests 或 docs 範例）
# - 定義 Ticket model
# - complete_structured(...) 回傳 Ticket 且欄位合理
# - 故意傳違反 Field 的輸入，確認重試後成功或拋 StructuredOutputError

# 3. 手動（本機 Ollama，模型需支援 tools）
ollama pull gemma4:e2b   # 或文件指定型號
# 執行結構化範例，確認 tool_calls 路徑可用
```

**通過條件**：

- [ ] `complete_structured` 在 mock 測試下穩定回傳 Pydantic 實例  
- [ ] 既有 `complete` / `Chat` / `stream=True` 測試 **全部仍通過**（無回歸）  
- [ ] `providers` 未依賴 `structured`  
- [ ] 文件與 `__all__` 匯出 `complete_structured`  

---

## 遷移影響

| 變更 | 消費方是否要改 |
|------|----------------|
| `from aicentral import complete, Chat` | 否 |
| 新增 `complete_structured` | 僅結構化需求者採用 |
| 新增必要依賴 `pydantic` | 是（pip 安裝 aicentral 時自動帶入） |
| `Chat.complete_structured` | 可選（P1） |

---

## 不在 v3.0 範圍

- 多供應商 fallback（v4.0）
- HTTP Gateway（v5.0）
- `acomplete` / 非同步結構化
- **結構化串流**（`complete_structured(..., stream=True)`、`Partial[T]`）——**刻意不做**，非技術不可行；理由見「結構化與串流」
- 內建 moderation / 額外 validation 管線（Instructor `validation/`）
- 修改 `aicentral-chat` 主流程（仍用 `Chat.complete(..., stream=True)` 即可）

---

## 與上游概念對照

| Instructor | aicentral v3.0 |
|------------|------------------|
| `client.chat.completions.create(response_model=User)` | `complete_structured(..., response_model=User)` |
| `from_provider("openai/...")` | 已有 `parse_model` + `registry`（v2.0） |
| `processing/response.py` | `structured/extract.py` + `validate.py` |
| 自動 retry on validation | `structured/retry` + `max_retries` |
| 多供應商 patch | **不做**；統一走 `complete()` |

---

## 實作順序建議

1. `structured/schema.py` + `test_schema.py`  
2. `providers/openai.py` raw 回傳（或 `return_raw`）  
3. `structured/extract.py` + `validate.py` + 測試  
4. `core/client.complete_structured` + 重試 + `test_complete_structured.py`  
5. `__init__.py` 匯出與文件  
6. （P1）`Chat.complete_structured`  
7. （P2）`mode=json` fallback + 本機 Ollama 手動驗收  

---

## 小結

| 問題 | 答案 |
|------|------|
| **現在**有結構化輸出嗎？ | **沒有**（v0.3.0）；僅 `complete()` / `Chat` 回傳文字 |
| v3.0 多出什麼？ | `complete_structured()` + `structured/*` + `pydantic` 依賴 |
| 領域 model 放哪？ | **消費方**；aicentral 只處理任意 `BaseModel` |
| 與 `complete()` 關係？ | 委派同一 provider 路徑，多加 tools 與驗證重試 |
| 結構化為何不支援串流？ | v3.0 **刻意不做**（驗證需完整 JSON、範圍控制）；v3.1+ 可評估 `Partial[T]` |
| 聊天要串流怎麼辦？ | 繼續用 `complete(stream=True)`，與結構化 API 分開 |
| 套件版本目標？ | **0.4.0**（實作完成後更新本文件狀態為「已實作」） |
| 下一步？ | 實作 v3.0 → v4.0 多供應商；或 v3.1 `acomplete_structured` / 結構化串流 |
