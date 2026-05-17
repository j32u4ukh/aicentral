# aicentral v2.0 實作紀錄

> 規格基線：[aicentral.md](./aicentral.md) · 上一版：[aicentral-v1.1.md](./aicentral-v1.1.md)  
> 狀態：**已實作**（函式庫 v0.3.0）

---

## 一句話

v2.0 **重構目錄**並加入 **`routing/parser` + `providers/registry`**；對外 `complete()`、`Chat()`、`stream=True` 不變，另支援 `model="ollama/gemma4:e2b"`。

---

## 交付範圍

| 項目 | 狀態 |
|------|------|
| `core/`（client、types、errors） | ✅ |
| `routing/parser.py` | ✅ |
| `providers/base.py`、`registry.py`、`openai.py` | ✅ |
| 裸名與 `ollama/` 前綴 model | ✅ |
| `complete` / `Chat` API 不變 | ✅ |
| `openai_compat` 相容匯入路徑 | ✅ |
| 測試 `tests/routing/` + 更新 patch 路徑 | ✅ 35 tests |

---

## 目錄結構（實作）

```
src/aicentral/
├── __init__.py
├── chat.py
├── client.py              # 向後相容 shim → core.client
├── types.py               # shim → core.types
├── exceptions.py          # shim → core.errors
├── core/
│   ├── client.py          # complete() + parse_model + registry
│   ├── types.py           # Message、ChatResponse
│   └── errors.py
├── providers/
│   ├── base.py
│   ├── registry.py        # ollama → openai
│   ├── openai.py          # 原 openai_compat 實作
│   ├── openai_compat.py   # 向後相容 re-export
│   └── streaming.py
└── routing/
    └── parser.py

tests/
├── routing/test_parser.py
└── …（其餘測試檔）
```

---

## 請求流程（v2.0）

```
complete(messages, model="ollama/gemma4:e2b", stream=?)
  → parse_model → ("ollama", "gemma4:e2b")
  → get_provider_module("ollama")
  → openai.chat_completions(_stream)(model="gemma4:e2b", …)
```

裸名 `gemma4:e2b` 視為 `ollama/gemma4:e2b`。

---

## 對外 API（新增匯出）

```python
from aicentral import complete, Chat, parse_model, ParsedModel

complete(messages=[...], model="ollama/gemma4:e2b")  # v2.0 建議寫法
complete(messages=[...], model="gemma4:e2b")         # 仍相容
```

---

## 遷移影響

| 變更 | 消費方是否要改 |
|------|----------------|
| `from aicentral import complete, Chat` | 否 |
| 深層 `aicentral.client` / `exceptions` / `types` | 否（shim 保留） |
| `aicentral.providers.openai_compat` | 否（轉發至 `openai`） |
| 明確 provider | 可選 `model="ollama/…"` |

---

## 小結

| 問題 | 答案 |
|------|------|
| 套件版本 | **0.3.0** |
| v2.0 多出什麼？ | 目錄骨架、model 路由、registry |
| 新功能？ | 幾乎無；Chat／串流／歷史仍為 v1.1 |
| 下一步 | v3.0 結構化輸出 |
