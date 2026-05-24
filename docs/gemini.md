這是一個非常經典且嚴重的 **Function Calling（工具宣告）格式不相容錯誤**。

簡單來說：**沒錯，你的程式提供給 Gemini 的資料格式完全錯了。你的程式正在用 OpenAI 的格式去餵給 Gemini，導致 Gemini 根本看不懂，氣得直接回傳 400 拒絕處理。**

從這幾行錯誤訊息可以看出關鍵：

> `Unknown name "type" at 'tools[0]'`
> `Unknown name "function" at 'tools[0]'`

---

### 🔍 為什麼會這樣？（OpenAI vs Gemini 格式衝突）

你的 `unity-mcp` 框架（可能是 LangGraph、LangChain 或某些大模型中介層 `aicentral-agent`）在將 Unity MCP 撈出來的 7 個 Tools（`tools[0]` 到 `tools[6]`）包裝成 API 請求時，使用了 **OpenAI 的標準規範**，但你現在後端接的是 **Gemini API**。

兩者的 JSON 結構差異如下：

#### ❌ 你的程式目前發出的格式（OpenAI 樣式 - 被 Gemini 拒絕）

OpenAI 要求外層必須有一個 `"type": "function"`，並且把具體資料塞在 `"function"` 欄位裡：

```json
// 這是 OpenAI 格式，Gemini 認不得 "type" 和 "function" 欄位！
"tools": [
  {
    "type": "function", 
    "function": {
      "name": "create_cube",
      "description": "建立一個 Cube",
      "parameters": { ... }
    }
  }
]

```

#### Gemini 真正期待的正確格式（Gemini 樣式）

Gemini 的 Function Calling 格式非常直接，最外層**沒有** `"type"` 與 `"function"`，而是直接把工具定義陣列放進 `functionDeclarations` 欄位中：

```json
"tools": [
  {
    "functionDeclarations": [
      {
        "name": "create_cube",
        "description": "建立一個 Cube",
        "parameters": { ... }
      }
    ]
  }
]

```

---

### 🛠️ 該如何修正這個問題？

這個問題通常出在你的 **`aicentral-agent`** 或 **`Chat.with_mcp`** 這層封裝組態上。

#### 檢查點一：大模型端點（Provider）設定錯誤

請檢查你的 Python 程式碼，初始化 LLM 的地方。你是不是雖然使用了 `gemini-flash` 模型，但底層卻錯誤地使用了 `ChatOpenAI` 的 Base URL（例如用 OpenAI 代理商、OpenAI 的 SDK 去疊代）？

* **如果是用 LangChain/LangGraph**：
請確保你呼叫的物件是 **`ChatGoogleGenerativeAI`**（來自 `@langchain/google-genai`）或官方的 Gemini 節點，而不是把 Gemini 的模型名稱硬填進 `ChatOpenAI(model="gemini-flash", base_url="...")`。

#### 檢查點二：MCP 工具轉換器（Converter）需要手動過濾

如果你使用的 Agent 框架不夠聰明，沒有自動幫你把 MCP 工具轉成 Gemini 格式，你在傳給 `Chat.with_mcp` 前，必須在 Python 程式碼中手動攔截並重構 `tools` 的 JSON 陣列。

**手動格式轉換邏輯（Python 概念範例）：**

```python
# 偽代碼：如果你的工具被強制包成了 OpenAI 格式，要在發送給 Gemini 前解包：
openai_tools = [...] # 這邊帶有 "type" 和 "function"

# 轉換成 Gemini 能接受的純粹 function 宣告
gemini_functions = []
for tool in openai_tools:
    if "function" in tool:
        gemini_functions.append(tool["function"])

# 最後包裝成 Gemini 的完美 tools 格式
gemini_payload_tools = [
    {
        "function_declarations": gemini_functions
    }
]

```

### 🎯 總結

1. **直接原因**：Gemini 收到一個帶有 `"type"` 和 `"function"` 欄位的 Tools 陣列，這在它的 API 規範中是「非法欄位（Unknown name）」。
2. **aicentral 已實作（LiteLLM 思路）**：MCP 編排仍產生 OpenAI `tools`；`providers/gemini.py` 發送前經 `providers/transform/gemini_tools.py` 轉成 `functionDeclarations`，回應 `functionCall` 再轉回 `tool_calls`。對話歷史中的 `tool` / `tool_calls` 由 `providers/transform/gemini.py` 的 `to_gemini_request` 處理。