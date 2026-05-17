# aicentral v1.1 規劃

> 規格基線：[aicentral.md](./aicentral.md) · 上一版實作紀錄：[aicentral-v1.0.md](./aicentral-v1.0.md)  
> 狀態：**規劃中**（尚未實作）

---

## 定位與目標

v1.0 已提供無狀態的 `complete(messages) → str`；多輪對話的 `messages` 列表由消費方（如 `aicentral-chat`）自行維護。v1.1 在**不破壞既有 `complete()` 簽名**的前提下，新增：

| 目標 | 說明 |
|------|------|
| **`Chat` 物件** | 對外統一表示「一則對話訊息」；同一型別可切換**有狀態** / **無狀態**兩種用法 |
| **內建歷史管理（有狀態時）** | 上限、修剪策略、可選壓縮，避免 context 無限膨脹 |
| **統一訊息語意** | `Message` 與 `providers/` 轉換，消費方不必關心各 API 的 role 差異 |

**一句話**：用一個 `Chat` 涵蓋「多輪累積歷史」與「單次問答」兩種場景；底層仍走 v1.0 的 `complete()` → Ollama，**不在 v1.1 實作 HTTP Gateway 啟動、客戶端分派或伺服器改寫**（留 v5.0）。

---

## 與其他版本的關係

```
v1.0  complete(messages)              ← 保留，無狀態
v1.1  Chat（stateful / stateless）+ 歷史策略
v2.0  core/types、routing/parser      ← v1.1 的 Message 可之後遷入 core/types
v3.0  complete_structured()
v5.0  AICENTRAL_MODE、gateway/、HTTP 客戶端與伺服器
```

| 項目 | v1.1 做 | v1.1 不做 |
|------|---------|-----------|
| `Chat` 有狀態 / 無狀態切換 | ✅ | |
| 有狀態時的歷史修剪 | ✅ | |
| `Message` + `providers` 轉換 | ✅ | |
| `complete(messages)` 向後相容 | ✅ | |
| `AICENTRAL_MODE`、HTTP Gateway **客戶端** | | ❌（v5.0） |
| 啟動 / 實作 `gateway/` **HTTP 伺服器** | | ❌（v5.0） |
| `transport/http_gateway.py` | | ❌（v5.0） |
| `routing/`、`complete_structured()` | | ❌（v2.0 / v3.0） |
| 串流 `stream=True` | | ❌ |
| 非 OpenAI 相容 provider | | ❌（v4.0） |

> **v5.0 預告（僅規劃參考，不納入 v1.1 驗收）**：屆時再以 `AICENTRAL_MODE` 讓 `complete()` / `Chat` 在「本機直連」與「HTTP 轉發 Gateway」間切換，消費方 API 不變。詳見 [aicentral.md](./aicentral.md) v5.0 與 [security.md](./security.md)。

---

## 交付範圍（驗收清單）

| 項目 | 優先 | 說明 |
|------|------|------|
| `Message` / `Chat` / `ChatMode` 與匯出 | P0 | 見下方 API |
| `Chat(stateful=True)` + `complete(prompt)` | P0 | 自動 append user / assistant |
| `Chat(stateful=False)` 單次問答 | P0 | 不累積歷史；每次僅送當輪 context |
| 執行期 `chat.stateful = False` 或 `set_mode()` | P1 | 同一實例可切換（見下節） |
| 歷史上限 + `drop_oldest_pair`（僅有狀態） | P0 | 預設策略 |
| `drop_oldest` 策略 | P0 | 最簡備選 |
| `complete(messages)` 向後相容 | P0 | 行為與 v1.0 一致 |
| `segment_compress` 策略 | P2 | 需額外 `complete` 做摘要 |
| `manual` + `delete()` / `trim()` | P1 | 僅有狀態模式有意義 |
| 單元測試（mock HTTP） | P0 | 不依賴真實 Ollama |
| 更新 `aicentral-chat` 改用 `Chat(stateful=True)` | P2 | 獨立 repo，不阻擋發版 |

---

## 核心概念：`Chat` 有狀態 vs 無狀態

### 為什麼放在同一個 `Chat` 型別

消費方常同時需要：

- **有狀態**：終端多輪聊天、客服 session，由物件代管 `messages`
- **無狀態**：每次 API 請求獨立、或 context 由外部 DB 組好再傳入

若拆成兩個類別，訊息組裝與 `providers` 轉換會重複。v1.1 以 **`ChatMode`**（或 `stateful: bool`）在同一物件上切換行為；模組級 `complete(messages)` 仍保留給「完全不要 `Chat` 實例」的場景。

### 模式對照

| | **有狀態** `stateful=True` | **無狀態** `stateful=False` |
|--|---------------------------|------------------------------|
| 預設 | ✅ `Chat()` 預設為有狀態 | 需明確指定 |
| 內部歷史 | 累積 `user` / `assistant` | **不**在 `complete()` 後寫入歷史 |
| `complete(prompt)` | 帶上既有歷史 + 本輪 user | 僅 `system`（若有）+ 本輪 user |
| `max_messages` / `HistoryPolicy` | 生效 | **忽略**（無歷史可修剪） |
| `messages` 屬性 | 反映累積紀錄 | 恆為空列表，或僅反映「本次請求暫存」快照 |
| 適用 | `aicentral-chat`、長對話 | 單次問答、外部自管 context |
| 與 v1.0 對應 | 取代手動 `messages.append` | 接近 `complete([{user}])`，但經統一 `Message` |

### 建議 API

```python
class ChatMode(str, Enum):
    STATEFUL = "stateful"
    STATELESS = "stateless"

class Chat:
    def __init__(
        self,
        *,
        mode: ChatMode = ChatMode.STATEFUL,   # 或 stateful: bool = True
        system: str | None = None,
        model: str | None = None,
        max_messages: int = 40,
        history_policy: HistoryPolicy = HistoryPolicy.DROP_OLDEST_PAIR,
    ) -> None: ...

    @property
    def mode(self) -> ChatMode: ...

    def set_mode(self, mode: ChatMode) -> None:
        """切換模式；由有狀態改無狀態時可選擇是否 clear() 歷史。"""

    # 便利建構（可選）
    @classmethod
    def stateful(cls, **kwargs: Any) -> Chat: ...
    @classmethod
    def stateless(cls, **kwargs: Any) -> Chat: ...
```

### 行為細節

**有狀態 `complete(user_input)`**：

```python
messages = [system?] + self._history + [{"role": "user", "content": user_input}]
reply = complete(messages=messages, model=self._model, system=None, **kwargs)
self._history += [user_msg, assistant_msg]
self._maybe_trim_history()
return reply
```

**無狀態 `complete(user_input)`**：

```python
messages = [system?] + [{"role": "user", "content": user_input}]
reply = complete(messages=messages, model=self._model, system=None, **kwargs)
# 不寫入 self._history
return reply
```

**無狀態但需帶入外部 context（單次）** — P1 可選 overload：

```python
reply = chat.complete(
    "總結以上",
    context=[{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}],
)
# context 僅用於本次請求，不寫入歷史
```

**執行期切換**（P1）：`set_mode(STATELESS)` 時建議預設 `clear()` 避免誤把舊歷史當成無狀態快取；若需保留可 `set_mode(STATELESS, keep_history=False)` 文件說明。

---

## `Message` 與 provider 轉換

不同後端的 role 或欄位可能不同。v1.1 **對外**只接受 aicentral 語意：

| `role` | 語意 |
|--------|------|
| `system` | 系統指示 |
| `user` | 使用者輸入 |
| `assistant` | 模型回覆 |

```python
from aicentral import Chat, ChatMode, Message

# 有狀態（預設）
chat = Chat(system="請用繁體中文回覆")
reply = chat.complete("台灣首都是？")

# 無狀態
chat_once = Chat(mode=ChatMode.STATELESS)
reply = chat_once.complete("用一句話介紹台灣")
```

**內部**：`providers/openai_compat.py` 負責 `list[Message] → OpenAI JSON`（可加 `to_openai_messages()`）；有狀態與無狀態共用同一條路徑。

### 與模組級 `complete(messages)` 的分工

| | `complete(messages)` | `Chat` 有狀態 | `Chat` 無狀態 |
|--|----------------------|---------------|---------------|
| 呼叫型態 | 函式 | 物件方法 | 物件方法 |
| 歷史 | 呼叫方每次傳入 | 物件自動累積 | 每次獨立，不保留 |
| 適用 | 腳本、已自管 `list[dict]` | 多輪聊天 | 單次問答、統一 `Message` 語意 |
| 底層 | `openai_compat` | 同上 | 同上 |

---

## `Chat` 類別設計（草案）

### 建議模組位置

```
src/aicentral/
├── __init__.py          # 匯出 complete, Chat, ChatMode, Message, HistoryPolicy
├── client.py            # complete()（v1.0 邏輯；v1.1 不拆 transport）
├── chat.py              # Chat、ChatMode、Message、HistoryPolicy、修剪邏輯
├── exceptions.py        # + HistoryOverflowError
└── providers/
    └── openai_compat.py # 既有；可加 to_openai_messages()
```

> v1.1 **不新增** `transport/`、`http_gateway.py`；HTTP 相關目錄留待 v5.0 與 `gateway/` 一併實作。

### 完整方法草案

```python
class Message(TypedDict):
    role: Literal["system", "user", "assistant"]
    content: str

class Chat:
    def __init__(self, *, mode: ChatMode = ChatMode.STATEFUL, ...) -> None: ...

    @property
    def messages(self) -> list[Message]:
        """有狀態：歷史快照；無狀態：空列表（或僅含未提交的暫存，實作時擇一並文件化）。"""

    def complete(
        self,
        user_input: str,
        *,
        context: list[Message] | None = None,  # 無狀態單次 context；P1
        **kwargs: Any,
    ) -> str: ...

    def clear(self) -> None: ...
    def delete(self, indices: Iterable[int]) -> None: ...   # 有狀態 + manual
    def trim(self, *, keep_last: int) -> None: ...
    def set_mode(self, mode: ChatMode, *, clear_on_stateless: bool = True) -> None: ...
```

模組級 `complete()` **維持 v1.0 簽名**；`Chat.complete()` 一律委派至該函式，不引入第二條 HTTP 路徑。

---

## 歷史紀錄管理（僅有狀態模式）

### 計數規則

- 僅當 `mode == STATEFUL` 時啟用 `max_messages` 與 `HistoryPolicy`。
- **`max_messages`**：只計 `user` + `assistant`；`system` 不計入上限。
- 修剪發生在**本次 `complete` 成功並寫入 assistant 之後**。

### 策略：`HistoryPolicy`

```python
class HistoryPolicy(str, Enum):
    DROP_OLDEST = "drop_oldest"
    DROP_OLDEST_PAIR = "drop_oldest_pair"   # 建議預設
    SEGMENT_COMPRESS = "segment_compress"   # P2
    MANUAL = "manual"                       # P1
```

| 策略 | 行為 | 額外 LLM 呼叫 |
|------|------|---------------|
| `drop_oldest` | 刪最舊 1 則 | 無 |
| `drop_oldest_pair` | 刪最舊一組 user+assistant | 無 |
| `segment_compress` | 區段壓成摘要訊息 | 有（P2） |
| `manual` | 超限拋 `HistoryOverflowError` | 無 |

### `segment_compress`（P2）

1. 固定窗口分區（例如每 5 則一組）。
2. 對每區段呼叫 `complete()` 做繁體中文摘要。
3. 以單則 `assistant` 摘要取代該區段。
4. 仍超限則 fallback `drop_oldest_pair`。

### 錯誤型別

```python
class HistoryOverflowError(AICentralError):
    """有狀態 + manual 策略下歷史超過 max_messages。"""
```

---

## 為什麼這樣設計

| 好處 | 說明 |
|------|------|
| **一個入口、兩種語意** | 同一 `Chat` 覆蓋多輪與單次，減少消費方學習成本 |
| **範圍可控** | v1.1 不碰 Gateway／`AICENTRAL_MODE`，避免與 v5.0 伺服器工作重疊 |
| **向後相容** | `complete(messages)` 不變；既有專案可漸進改用 `Chat` |
| **職責清晰** | 歷史語意進有狀態 `Chat`；無狀態與 v1.0 函式對齊 |
| **為 v5.0 鋪路** | `Chat` / `Message` 穩定後，v5.0 只需在 `client.complete` 底層加分派，不需改消費方 |

---

## 目錄結構（v1.1 目標）

```
src/aicentral/
├── __init__.py
├── client.py
├── chat.py
├── exceptions.py
└── providers/
    └── openai_compat.py

tests/
├── test_complete.py     # 既有
├── test_chat.py         # 有狀態累積、無狀態不保留
├── test_chat_mode.py    # set_mode、stateful/stateless 切換
└── test_history.py      # HistoryPolicy（有狀態）
```

---

## 使用範例

### 有狀態多輪（預設）

```python
from aicentral import Chat, HistoryPolicy

chat = Chat(
    max_messages=20,
    history_policy=HistoryPolicy.DROP_OLDEST_PAIR,
)

print(chat.complete("我叫小明"))
print(chat.complete("我剛剛說我叫什麼？"))
```

### 無狀態單次

```python
from aicentral import Chat, ChatMode

chat = Chat(mode=ChatMode.STATELESS, system="請用繁體中文回覆")
print(chat.complete("用一句話介紹台灣"))
print(chat.complete("上一句話是什麼？"))  # 模型看不到上一輪，除非你自己傳 context
```

### 執行期切換（P1）

```python
chat = Chat()
chat.complete("記住：代號 Alpha")
chat.set_mode(ChatMode.STATELESS)  # 預設 clear 歷史
chat.complete("我的代號是？")       # 不會記得 Alpha
```

### 仍可直接用 v1.0 函式

```python
from aicentral import complete

reply = complete(messages=[{"role": "user", "content": "你好"}])
```

### `aicentral-chat` 遷移（P2）

```python
chat = Chat()  # 預設有狀態
reply = chat.complete(user_input)
```

錯誤時 rollback 最後一則 `user`：在 `Chat.complete` 內封裝，與現行 `messages.pop()` 一致。

---

## 測試策略

| 類型 | 做法 |
|------|------|
| 單元 | mock `openai_compat` / `httpx`，不依賴 Ollama |
| 有狀態 | `max_messages=4`，連續 `complete` 後斷言長度與內容 |
| 無狀態 | 連續兩次 `complete`，斷言第二次請求的 `messages` 不含第一輪 |
| 模式切換 | `set_mode` 後行為符合預期 |
| `segment_compress` | mock 摘要回傳（P2） |

---

## 遷移與相容性

| 變更 | 影響 |
|------|------|
| 新增 `Chat`、`ChatMode`、`Message` | 僅新增匯出 |
| `complete(messages, ...)` | **簽名與回傳不變** |
| 無新增 Gateway 相關 env | 現有 `.env` 僅 `OLLAMA_*` 即可 |
| `aicentral-chat` | 建議 `Chat()` 有狀態，非強制 |

---

## 已知限制（v1.1 接受）

- 不實作 `AICENTRAL_MODE`、HTTP Gateway 客戶端與**啟動 HTTP 伺服器**（皆 v5.0）。
- `segment_compress` 為最佳努力，非審計級紀錄。
- 無 `acomplete()` / 串流。
- `Message` 僅 `content: str`（無 multimodal / tool calls）。
- 無狀態模式不跨請求記憶；跨程序 session 需消費方自管或等 v5.0 Gateway。

---

## 實作順序建議

1. **`Message` + `Chat` 有狀態（無修剪）** — 自動累積歷史  
2. **`Chat` 無狀態模式** — 不寫入歷史  
3. **`DROP_OLDEST_PAIR` + `max_messages`**（僅有狀態）  
4. **`manual` + `delete` / `HistoryOverflowError`**  
5. **`set_mode` 執行期切換**（P1）  
6. **無狀態 `context` 參數**（P1）  
7. **`segment_compress`（P2）**  
8. **文件與 `aicentral-chat` 範例**

---

## 開放問題（實作前可決策）

| 問題 | 建議 |
|------|------|
| `ChatMode` 還是 `stateful: bool`？ | 對外文件用 `ChatMode`；內部可映射 bool |
| 無狀態 `messages` 屬性回傳什麼？ | 固定回傳 `[]`，避免誤以為有歷史 |
| `set_mode(STATELESS)` 是否一律 `clear()`？ | 預設 `clear_on_stateless=True` |
| `Message` 用 `TypedDict` 還是 dataclass？ | v1.1 `TypedDict`；v2.0 遷 `core/types` |

---

## 小結

| 問題 | 答案 |
|------|------|
| v1.1 要做什麼？ | **`Chat` 有狀態/無狀態切換** + **有狀態歷史策略** + **`Message` 統一語意** |
| 與 v1.0 關係？ | **保留** `complete(messages)`；`Chat` 為增量能力 |
| HTTP / Gateway？ | **全部不在 v1.1**；`AICENTRAL_MODE` 與 Gateway 伺服器屬 **v5.0** |
| 消費方怎麼選？ | 多輪 → `Chat()` 或 `Chat.stateful()`；單次 → `Chat(mode=STATELESS)` 或繼續 `complete(messages)` |

實作時以 P0 驗收為準：**有狀態 `Chat` + `drop_oldest_pair` + 無狀態不切換歷史** 測試全綠；HTTP 相關改寫留待 v5.0。
