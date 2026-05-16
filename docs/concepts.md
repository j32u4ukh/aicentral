# 核心概念說明

> 架構與版本規劃見 [aicentral.md](./aicentral.md)。  
> 本文用白話說明 **aicentral 在做什麼**，以及 **`complete()` 的用途**。

---

## aicentral 是什麼？

一句話：**幫你的 Python 專案「用同一種方式」呼叫大語言模型，而不必自己處理 HTTP、網址、模型名稱等細節。**

- 你是**後端、腳本、或像 `aicentral-chat` 這樣的範例專案**
- 你只想問模型一句話、拿到一段文字回覆
- 你**不**想在每個專案裡重寫「組 JSON → 打 API → 解析回應」

aicentral 就是夾在中間的**能力層（library）**：

```
你的程式  →  aicentral.complete()  →  Ollama（或其它 API）
```

它**不是**聊天網站、**不是**業務系統；對話迴圈、網頁 UI、訂單邏輯等都應放在**引用 aicentral 的專案**裡。

---

## `complete()` 到底在幹嘛？

`complete()` 的名字來自業界常說的 **「completion」**（補全／續寫）：給模型一段對話上下文，讓它**生成下一段回覆**。

### 它做的一件事

**輸入**：一串對話訊息（`messages`）+ 要用哪個模型（`model`）  
**輸出**：模型回的那一段**純文字**（助理的 `content`）

```python
from aicentral import complete

text = complete(
    messages=[
        {"role": "user", "content": "用一句話介紹台灣"},
    ],
    model="llama3.2",
)
print(text)
```

你可以把它想成：

> 「幫我把這段對話送給大模型，把助理說的話字串拿回來。」

### 背後實際發生了什麼（v0.1）

`complete()` **本身不會推理**；它只負責**代送與代收**：

1. 讀取設定（例如 `.env` 裡的 `OLLAMA_BASE_URL`、`OLLAMA_MODEL`）
2. 把 `messages` 包成 OpenAI 相容的 JSON body
3. 用 HTTP `POST` 打到 Ollama 的 `/v1/chat/completions`
4. 從回應 JSON 取出 `choices[0].message.content`
5. 把這段字串回傳給你的程式

```
complete()
  ├─ 決定用哪個 model
  ├─ 組請求（OpenAI 格式）
  ├─ httpx → Ollama
  └─ 解析 → 回傳 str
```

也就是說：**大模型在 Ollama 裡算；`complete()` 負責通訊與格式統一。**

---

## `messages` 是什麼？

`messages` 是一個**對話紀錄列表**，每一則有 `role` 與 `content`：

| role | 通常代表 |
|------|----------|
| `system` | 給模型的整體指示（人設、規則） |
| `user` | 使用者說的話 |
| `assistant` | 模型先前回過的話（多輪對話時要帶上） |

範例（單輪）：

```python
messages = [{"role": "user", "content": "你好"}]
```

範例（多輪 — 由**你的程式**維護歷史，再整包傳給 `complete()`）：

```python
messages = [
    {"role": "user", "content": "我叫小明"},
    {"role": "assistant", "content": "你好小明！"},
    {"role": "user", "content": "我剛剛說我叫什麼？"},
]
reply = complete(messages=messages, model="llama3.2")
```

aicentral v0.1 **不會**自動記住上一輪對話；要連續聊天，需在 `aicentral-chat` 等專案裡自己 append `user` / `assistant` 訊息。

---

## 為什麼不直接在專案裡打 Ollama？

可以，但每個專案都要重複：

- 記住 API 路徑、`base_url`、模型名稱
- 處理 HTTP 錯誤、逾時、JSON 解析
- 日後若改連 OpenAI 雲端，又要改一輪程式

透過 `complete()`：

| 好處 | 說明 |
|------|------|
| **單一入口** | 業務程式只認 `complete()`，不認 Ollama / OpenAI 細節 |
| **設定集中** | URL、預設模型放在 `.env`，少硬編碼 |
| **日後可擴充** | v0.4 換雲端 API、v0.3 加結構化輸出時，消費方程式改動小 |

這和 [LiteLLM](./litellm.md) 的 `completion()` 精神類似，只是 aicentral 做更輕量的自研實作。

---

## `complete()` 適合 / 不適合做什麼

### 適合

- 終端機聊天（`aicentral-chat`）
- 後端「問 LLM 一句話拿答案」
- 簡單摘要、翻譯、分類（回覆是**自由文字**即可）

### 目前不適合（請等後續版本或自行處理）

| 需求 | 說明 |
|------|------|
| 回傳固定 JSON / 欄位 | 用 v0.3 的 `complete_structured()`（規劃中） |
| 串流逐字輸出 | v0.1 未支援 `stream=True` |
| 嵌入向量、生圖 | 非 chat completion 範圍 |
| 自動記憶多輪 session | 需在消費方自己管 `messages` 列表 |

---

## 和 `complete_structured()` 的差別（預告）

| | `complete()` | `complete_structured()`（v0.3） |
|--|--------------|--------------------------------|
| 回傳 | `str` 自由文字 | Pydantic model 實例 |
| 用途 | 聊天、開放式問答 | 抽取、分類、固定 schema |
| 底層 | 同一條 HTTP 呼叫模型 | 同一條，外加 schema 與驗證 |

兩者都應走 aicentral，而不是在業務專案裡混用兩套 HTTP 客戶端。詳見 [instructor.md](./instructor.md) 的設計思想。

---

## 和 `aicentral-chat` 的關係

| 層級 | 負責 |
|------|------|
| **aicentral** | `complete()`：怎麼跟模型說話 |
| **aicentral-chat** | `while True` 讀輸入、累積 `messages`、印出回覆 |

`aicentral-chat` 是**消費方**：示範「如何正確依賴函式庫」。  
你不一定要在 chat 專案裡寫 HTTP；只呼叫 `complete()` 即可。

---

## 常見問題

### `model="llama3.2"` 一定要寫嗎？

不寫時可用環境變數 `OLLAMA_MODEL`。傳參數會覆蓋預設值。

### 為什麼叫 OpenAI 相容卻用 Ollama？

Ollama 提供與 OpenAI **相同路徑與 JSON 格式** 的 API，所以實作一份相容 client 即可，無需兩套協定。v0.1 把 `base_url` 指到本機 Ollama。

### `complete()` 會幫我存對話嗎？

不會。每次呼叫都是獨立 HTTP 請求；歷史由呼叫方放進 `messages`。

### 出錯時會怎樣？

v0.1 規劃為拋出例外（例如連不上 Ollama、模型不存在）。v0.2 起會有較完整的 `errors` 模組。呼叫方可用 `try/except` 處理。

---

## 延伸閱讀

- [aicentral.md](./aicentral.md) — 版本規劃、目錄、Ollama 設定
- [litellm.md](./litellm.md) — 上游「統一 completion」概念
- [instructor.md](./instructor.md) — 上游「結構化輸出」概念
