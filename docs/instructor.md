# Instructor 框架概述

> 上游專案：[567-labs/instructor](https://github.com/567-labs/instructor)（原 jxnl/instructor）  
> 官方文件：<https://python.useinstructor.com>

## 是什麼

Instructor 是在 LLM 呼叫之上加上 **Pydantic 結構化輸出** 的函式庫：你定義 `BaseModel`，它負責把模型回傳內容解析、驗證並轉成型別安全的 Python 物件，減少手寫 JSON schema、重試與錯誤處理。

## 解決的問題

| 沒有 Instructor | 有 Instructor |
|-----------------|---------------|
| 手寫 tool / JSON schema | 用 Pydantic model 描述輸出 |
| 自行 parse、validate、retry | 內建驗證失敗重試 |
| 各供應商 API 差異大 | `from_provider()` 統一入口 |

## 核心用法

```python
import instructor
from pydantic import BaseModel


class User(BaseModel):
    name: str
    age: int


client = instructor.from_provider("openai/gpt-4o-mini")
user = client.chat.completions.create(
    response_model=User,
    messages=[{"role": "user", "content": "John is 25 years old"}],
)
# user 已是驗證過的 User 實例
```

常見入口：

- `instructor.from_provider("openai/gpt-4o-mini")` — 推薦，依字串選供應商
- `instructor.from_openai(client)` / `from_litellm(...)` — 包裝既有 client
- `instructor.patch(client)` — 對現有 client 打補丁（舊寫法）

## 程式庫目錄結構（`instructor/instructor/`）

```
instructor/
├── providers/     # 各 LLM 供應商適配（openai、anthropic、gemini…）
├── core/          # Instructor / AsyncInstructor client、patch 邏輯
├── processing/    # 回應解析、schema 產生、function call 處理
├── dsl/           # 進階型別：Partial、IterableModel、Maybe 等
├── validation/    # 額外驗證（如 moderation）
├── batch/         # 批次請求
└── cache/         # 快取
```

**閱讀建議**：從 `from_provider` → `core/client.py` → `processing/response.py` 追一條請求即可掌握主流程。

## 與 LiteLLM 的關係

- Instructor **不負責**多供應商路由或 Gateway；它專注在**輸出結構化**。
- 可與 LiteLLM 搭配：`instructor.from_litellm(...)` 或先走 LiteLLM Proxy，再用 Instructor 包一層。
- aicentral 的典型分工：**LiteLLM 管「打哪個模型」**，**Instructor 管「回傳什麼型別」**。

## 與 aicentral 的關係

- aicentral **參考** Instructor 設計，在 `structured/` 內自行實作，**不安裝** `instructor` 套件。
- 領域 Pydantic model 定義在**消費方專案**；aicentral 提供 `complete_structured(response_model=...)`。
- 需要嚴格 schema 時，由消費方透過 aicentral 取得結構化結果，而非自行解析 JSON。
