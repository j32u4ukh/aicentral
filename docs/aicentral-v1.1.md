# aicentral v1.1 實作紀錄

> 規格基線：[aicentral.md](./aicentral.md) · 上一版：[aicentral-v1.0.md](./aicentral-v1.0.md)  
> 狀態：**已實作**（函式庫 v0.2.0；`aicentral-chat` 遷移仍為消費方 P2）

---

## 交付範圍

| 項目 | 優先 | 狀態 |
|------|------|------|
| `Message` / `Chat` / `ChatMode` / `HistoryPolicy` | P0 | ✅ |
| `Chat` 有狀態 + `complete(prompt)` | P0 | ✅ |
| `Chat` 無狀態 | P0 | ✅ |
| `drop_oldest` / `drop_oldest_pair` | P0 | ✅ |
| `complete(messages)` 向後相容 | P0 | ✅ |
| `complete(..., stream=True)` | P1 | ✅ |
| `Chat.complete(..., stream=True)` | P1 | ✅ |
| `set_mode()` 執行期切換 | P1 | ✅ |
| 無狀態 `context=` | P1 | ✅ |
| `manual` + `delete()` / `trim()` | P1 | ✅ |
| `segment_compress` | P2 | ✅ |
| `providers/streaming.py` SSE 解析 | P1 | ✅ |
| 單元測試（mock HTTP / SSE） | P0 | ✅ 29 tests |
| `aicentral-chat` 改用 `Chat` | P2 | ⏳ 獨立 repo |
| `AICENTRAL_MODE` / HTTP Gateway | — | ❌ v5.0 |
| `acomplete` 非同步串流 | — | ❌ v1.2+ |

---

## 目錄與檔案（實作）

```
src/aicentral/
├── __init__.py              # complete, Chat, ChatMode, HistoryPolicy, Message, 例外
├── client.py                # complete(stream=False|True)
├── chat.py                  # Chat 有/無狀態、歷史修剪、串流
├── types.py                 # Message TypedDict
├── exceptions.py            # + HistoryOverflowError
└── providers/
    ├── openai_compat.py     # chat_completions + chat_completions_stream
    └── streaming.py         # parse_sse_data_line、extract_delta_content

tests/
├── test_complete.py
├── test_chat.py
├── test_chat_mode.py
├── test_history.py
└── test_stream.py
```

---

## 定位摘要

v1.1 在 v1.0 `complete(messages) → str` 之上新增：

| 能力 | 說明 |
|------|------|
| **`Chat`** | 同一型別切換**有狀態** / **無狀態**（`ChatMode`） |
| **歷史管理** | 僅有狀態：`max_messages`、`HistoryPolicy`（含 `segment_compress`） |
| **回應模式** | `stream=False`（預設，全文 `str`）／`stream=True`（`Iterator[str]`） |

底層仍直連 Ollama OpenAI 相容 API；預設模型 **gemma4:e2b**（`OLLAMA_MODEL`）。

---

## 請求流程

### 完整回答（預設）

```
complete(messages, stream=False)
  → _with_system_prompt()
  → openai_compat.chat_completions()
  → POST {base_url}/chat/completions  (stream: false)
  → choices[0].message.content → str
```

### 串流

```
complete(messages, stream=True)
  → _with_system_prompt()
  → openai_compat.chat_completions_stream()
  → POST ... (stream: true)
  → iter_lines → parse_sse_data_line → extract_delta_content
  → yield str 增量

Chat.complete(prompt, stream=True)  # 有狀態
  → 同上 yield 增量
  → 迭代結束後 append 一則完整 assistant → _maybe_trim_history()
```

---

## 對外 API

```python
from aicentral import Chat, ChatMode, HistoryPolicy, Message, complete

# 有狀態多輪
chat = Chat(max_messages=20, history_policy=HistoryPolicy.DROP_OLDEST_PAIR)
print(chat.complete("我叫小明"))

# 無狀態
once = Chat(mode=ChatMode.STATELESS)
print(once.complete("用一句話介紹台灣"))

# 串流
for part in complete(messages=[{"role": "user", "content": "你好"}], stream=True):
    print(part, end="", flush=True)

for part in chat.complete("介紹台灣", stream=True):
    print(part, end="", flush=True)

# v1.0 相容
text = complete(messages=[{"role": "user", "content": "你好"}])
```

---

## 與 LiteLLM 的對照（串流）

| LiteLLM | aicentral v1.1 |
|---------|----------------|
| `completion(..., stream=False)` | `complete(..., stream=False)` → `str` |
| `completion(..., stream=True)` | `complete(..., stream=True)` → `Iterator[str]` |
| `chunk.choices[0].delta.content` | 迭代器元素為已抽取的 **delta 字串** |

---

## 環境變數

| 變數 | 預設 | 用途 |
|------|------|------|
| `OLLAMA_BASE_URL` | `http://localhost:11434/v1` | OpenAI 相容 API |
| `OLLAMA_MODEL` | `gemma4:e2b` | 預設模型 |
| `OLLAMA_API_KEY` | `ollama` | Bearer（本機可省略） |
| `AICENTRAL_SYSTEM_PROMPT` | 內建繁體中文提示 | `complete` / `Chat` 自動插入 system |

---

## 測試策略（已執行）

```powershell
cd aicentral
pip install -e ".[dev]"
pytest   # 29 passed，不依賴真實 Ollama
```

| 測試檔 | 涵蓋 |
|--------|------|
| `test_complete.py` | 非串流、`system` 插入 |
| `test_chat.py` | 有/無狀態、修剪、rollback |
| `test_chat_mode.py` | `set_mode` |
| `test_history.py` | `manual`、`segment_compress` |
| `test_stream.py` | SSE 解析、`stream=True`、`Chat` 串流歷史 |

---

## 已知限制

- 無 `acomplete()` / 非同步串流。
- 串流中途取消迭代不寫入有狀態歷史；中途 `ProviderError` 亦不寫入。
- `Message` 僅 `content: str`（無 multimodal / tool calls）。
- 不實作 Gateway／`AICENTRAL_MODE`（v5.0）。

---

## 與其他版本

```
v1.0  complete(messages) → str
v1.1  Chat + 歷史策略 + stream（本版）
v2.0  core/types、routing/parser
v3.0  complete_structured()
v5.0  AICENTRAL_MODE、gateway/
```

---

## 規劃原文（存檔）

以下為實作前規劃細節，多數已落地；差異以本文件上方「交付範圍」為準。

<details>
<summary>展開 v1.1 規劃原文</summary>

### 核心：`Chat` 有狀態 vs 無狀態

| | 有狀態 | 無狀態 |
|--|--------|--------|
| 預設 | `Chat()` | `Chat(mode=ChatMode.STATELESS)` |
| 歷史 | 自動累積 | 不寫入 |
| `messages` 屬性 | 歷史快照 | 恆 `[]` |

### 歷史策略（僅有狀態）

- `drop_oldest`、`drop_oldest_pair`（預設）、`segment_compress`、`manual`
- 超限 `manual` → `HistoryOverflowError`

### 回應模式

- `stream=False`：全文 `str`
- `stream=True`：`Iterator[str]`；有狀態 Chat 在迭代結束後寫入完整 assistant

### v1.1 不做

- HTTP Gateway 伺服器／客戶端、`AICENTRAL_MODE`
- `acomplete`、非 OpenAI 相容 provider

</details>

---

## 小結

| 問題 | 答案 |
|------|------|
| v1.1 做了什麼？ | `Chat` 有/無狀態、歷史策略、`stream=False\|True` |
| 套件版本？ | **0.2.0** |
| 消費方怎麼選？ | 多輪 `Chat()`；單次 `STATELESS`；即時 UI `stream=True` |
| 下一步？ | `aicentral-chat` 改用 `Chat`（P2）；v5.0 Gateway |
