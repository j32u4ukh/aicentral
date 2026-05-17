# aicentral v2.0 規劃

> 規格基線：[aicentral.md](./aicentral.md) · 上一版實作：[aicentral-v1.1.md](./aicentral-v1.1.md)  
> 狀態：**規劃中**（尚未實作）

---

## 一句話

v2.0 **幾乎不增加新功能**，主要是**重構目錄**與**統一 model 字串路由**；對外仍用 `complete()`、`Chat()`、`stream=True`，消費方程式可不改或只改 model 寫法。

---

## 相對於前版多出什麼？

| 版本已有 | v2.0 新增 |
|----------|-----------|
| v1.0 `complete(messages) → str` | 保留；入口改在 `core/client.py` |
| v1.1 `Chat`、歷史策略、串流 | 保留；`chat.py` 可留根目錄 |
| v1.1 `Message`（`types.py`） | 遷入 `core/types.py`，可補 `ChatResponse` 等型別 |
| v1.1 `exceptions.py` | 遷入 `core/errors.py` |
| model 裸名 `gemma4:e2b` + `OLLAMA_*` | **`routing/parser`**：`ollama/gemma4:e2b` → (provider, model_id) |
| 單一 `openai_compat.py` | **`providers/base` + `registry`**，便於 v4.0 加第二家 |
| 測試平鋪在 `tests/` | 依模組分子目錄 |

**v2.0 不做**（留後續版本）：

| 項目 | 版本 |
|------|------|
| `complete_structured()` / Pydantic | v3.0 |
| 雲端 OpenAI、Anthropic、fallback | v4.0 |
| `AICENTRAL_MODE`、HTTP Gateway | v5.0 |
| `acomplete` 非同步 | v2.1 或併入 v2.0 P2（可選） |

---

## 現況（v1.1）→ v2.0 對照

```
v1.1 現況                          v2.0 目標
─────────────────────────────────────────────────────────
src/aicentral/client.py      →    core/client.py
src/aicentral/types.py       →    core/types.py
src/aicentral/exceptions.py  →    core/errors.py
src/aicentral/chat.py        →    chat.py（不變或微調 import）
providers/openai_compat.py   →    providers/openai.py + base/registry
（無）                       →    routing/parser.py
```

對外匯出（`from aicentral import …`）**維持不變**：`complete`、`Chat`、`Message`、`ChatMode`、`HistoryPolicy`、例外類別。

---

## 目錄結構（目標）

```
src/aicentral/
├── __init__.py          # 轉發 core / chat 的公開 API
├── chat.py              # v1.1 已有，邏輯不變
├── core/
│   ├── client.py        # complete(stream=…)、_with_system_prompt
│   ├── types.py         # Message、Role、（可選）ChatResponse
│   └── errors.py        # AICentralError、ProviderError、HistoryOverflowError
├── providers/
│   ├── base.py          # Provider 介面或協定
│   ├── registry.py      # 依 provider 名稱選實作
│   ├── openai.py        # 由原 openai_compat 遷入或重新匯出
│   └── streaming.py       # SSE 解析（可留原位置）
└── routing/
    └── parser.py        # 解析 model 字串

tests/
├── test_complete.py     # 或 tests/core/
├── test_chat*.py
├── test_stream.py
├── providers/
└── routing/
```

---

## 核心產出說明

### 1. `routing/parser.py`（使用者可感知的主要變化）

| 寫法 | v1.1 | v2.0 |
|------|------|------|
| 省略 model | 用 `OLLAMA_MODEL`（裸名） | 同左；parser 可視為 `ollama/{OLLAMA_MODEL}` |
| 裸名 `gemma4:e2b` | ✅ 直送 Ollama | ✅ 向後相容（視為本機預設 provider） |
| `ollama/gemma4:e2b` | ❌ 不解析 | ✅ 明確指定 provider + model_id |

```python
# v2.0 建議寫法（與 LiteLLM 類似）
complete(messages=[...], model="ollama/gemma4:e2b")
chat = Chat(model="ollama/gemma4:e2b")
```

parser 輸出示例：`("ollama", "gemma4:e2b")` → registry 選 OpenAI 相容 adapter → 沿用現有 HTTP 路徑。

### 2. `providers/registry`（內部擴展性）

- v1.1：寫死 `openai_compat.chat_completions(…)`
- v2.0：`complete` → parser → `registry.get("ollama")` → 對應 provider
- v4.0 加雲端時只增 provider 模組與 registry 註冊，不改 `Chat` / `complete` 簽名

### 3. `core/types`（型別集中）

- 將根目錄 `types.py`、`exceptions.py` 收斂到 `core/`
- 可選：為非串流回應加 `ChatResponse`（content、model 等），**不強制**消費方改用

---

## 交付範圍（驗收）

| 項目 | 優先 | 說明 |
|------|------|------|
| 目錄遷移 `core/`、`routing/` | P0 | 行為與 v1.1 一致 |
| `routing/parser` + 裸名相容 | P0 | `ollama/x` 與 `x` 皆可 |
| `providers/registry` | P0 | 至少註冊 `ollama` |
| `complete` / `Chat` 對外 API 不變 | P0 | 含 `stream=True` |
| 測試搬遷 + parser/registry 單測 | P0 | 29+ 既有測試仍綠 |
| 文件與 `.env.example` 補 `ollama/` 範例 | P1 | |
| `acomplete` | P2 | 可選，非 v2.0 必要 |

---

## 遷移影響（消費方）

| 變更 | 是否需要改程式 |
|------|----------------|
| `from aicentral import complete, Chat` | 否 |
| `complete(messages=…)`、`Chat().complete(…, stream=True)` | 否 |
| `model="gemma4:e2b"` | 否（相容） |
| 想明確標 provider 時 | 可選改 `model="ollama/gemma4:e2b"` |

---

## 小結

| 問題 | 答案 |
|------|------|
| v2.0 多出什麼能力？ | **幾乎沒有新能力**；主要是**好維護**與 **`provider/model` 路由** |
| 和 v1.1 差在哪？ | 目錄骨架、registry、parser；**Chat／串流／歷史 v1.1 已有** |
| 下一步版本？ | v3.0 結構化輸出；v4.0 多供應商；v5.0 Gateway |

實作時以「**重構後測試全綠 + `ollama/gemma4:e2b` 可呼叫**」為驗收；新功能留給 v3.0 起。
