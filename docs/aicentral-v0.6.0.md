# aicentral v0.6.0 — MCP 工具編排（Library）

> 總覽：[aicentral.md](./aicentral.md) · MCP 使用：[mcp.md](./mcp.md) · 前置：**0.5.0**（`MCPManager`、`mcp_servers` yaml）  
> 下一階段（可選）：[aicentral-v0.6.1.md](./aicentral-v0.6.1.md)（Proxy HTTP）

**套件版本**：`0.6.0`（實作完成後更新 `pyproject.toml`）

---

## 目標

在 **不新增 MCP Server、不實作 OAuth** 的前提下，讓 `complete()` / `Chat` 能跑通最小 **tool loop**：

1. 從 yaml 設定的 MCP server **列出工具**（含 `description`、`inputSchema`）。
2. 將工具轉成模型可用的 **OpenAI function `tools`** 格式。
3. 模型回傳 `tool_calls` 時，由 aicentral **代呼** `MCPManager.call_tool`。
4. 將 tool 結果以 `role: tool` 併回 `messages`，**再呼叫** `complete()`，直到模型回文字或達上限。

**定位**：aicentral 仍是 **MCP Client**；工具語意由遠端 MCP Server 提供，無需 SKILL 類文件（見 `mcp/manager.py` 模組說明）。

---

## 範圍

### 要做

| 項目 | 說明 |
|------|------|
| `mcp/orchestrator.py`（或 `mcp/tools.py`） | MCP 工具 → OpenAI function schema；解析 `tool_calls` → `call_tool` |
| `complete(..., mcp_servers=...)` 或等價參數 | 啟用 MCP 編排；與既有 `**kwargs`（如 provider 的 `tools`）協調 |
| `Chat` 可選開關 | 例如 `mcp_servers: list[str] \| "all"`、`max_tool_rounds: int` |
| 錯誤 | `MCPError` 不觸發 LLM `fallback`；編排失敗可包成 `ProviderError` 或獨立拋出 |
| 測試 | mock `MCPManager` / mock provider，單元 + 一輪整合 |
| 文件 | 更新 [mcp.md](./mcp.md)、本文件驗收勾選 |

### 刻意不做（保持輕量）

- MCP OAuth2 / PKCE、semantic tool filter、registry 市集
- 在 `gateway/` 暴露 HTTP（屬 **0.6.1**）
- 串流模式下的即時 tool loop（v0.6.0 可限定 **非串流** 或文件標明不支援）
- 將 MCP 註冊為 `providers/mcp` LLM

---

## 架構

```
complete(messages, mcp_servers=["deepwiki"])
  │
  ├─ mcp/orchestrator
  │     ├─ MCPManager.list_tools / list_all_tools
  │     ├─ to_openai_tools(mcp_tool_dicts)
  │     └─ handle_tool_calls → call_tool → Message(role=tool)
  │
  └─ core/client.complete (既有 routing → providers)
        └─ 僅在無 tool_calls 時結束；有 tool_calls 則迴圈
```

**依賴方向**：`core` → `mcp/orchestrator` → `mcp/manager`；`mcp` **不** import `providers`。

---

## API 草案

### `complete()`

```python
from aicentral import complete

reply = complete(
    messages=[{"role": "user", "content": "查一下 aicentral  repo 的 README 重點"}],
    model="local-chat",  # 或雲端；須支援 tools / tool_calls
    mcp_servers=["deepwiki"],  # yaml 中的 server 名稱；或 mcp_servers="all"
    max_tool_rounds=5,         # 預設 5，防止無限迴圈
)
# reply: str（最終助理文字）
```

| 參數 | 型別 | 說明 |
|------|------|------|
| `mcp_servers` | `list[str] \| Literal["all"] \| None` | `None` = 不啟用 MCP 編排（與 0.5.0 行為相同） |
| `max_tool_rounds` | `int` | 單次 `complete()` 內最多幾輪「模型 → tool → 模型」 |
| `tools` | — | 若消費方自行傳入一般 function `tools`，與 MCP 工具**合併**或文件約定互斥（實作時二選一並寫清） |

### `Chat`

```python
from aicentral import Chat

chat = Chat(
    model="local-chat",
    mcp_servers=["deepwiki"],
    max_tool_rounds=5,
)
reply = chat.complete("幫我搜尋 MCP 協定是什麼")
```

有狀態時：tool 訊息是否寫入 `_history` 由實作決定；**建議**僅保留最終 user/assistant 對，或提供 `include_tool_messages_in_history: bool` 預設 `False`。

### MCP 工具識別（內部）

沿用 0.5.0：

- yaml `mcp_servers.<name>`
- 別名 URL：`aicentral/mcp/<name>`（`MCPManager.parse_server_url`）
- 工具名：`tool_name_prefix=true` 時為 `<server>__<tool>`

---

## 實作任務清單

| # | 任務 | 產出 |
|---|------|------|
| 1 | `mcp_tools_to_openai()` | 將 `list_tools` 結果轉 `{type,function:{name,description,parameters}}` |
| 2 | `run_tool_calls()` | 解析 assistant `tool_calls` → `MCPManager.call_tool` → `role: tool` messages |
| 3 | `complete_with_mcp_loop()` | 包在 `core/client.py` 或 orchestrator 內；呼叫既有 `complete_with_fallback` |
| 4 | `Chat` 參數與委派 | `mcp_servers`、`max_tool_rounds` 傳入底層 |
| 5 | Provider 能力檢查 | 不支援 tools 的 model → 清楚 `ValueError` / `ProviderError` |
| 6 | `tests/mcp/test_orchestrator.py` | mock list/call、一輪 loop |
| 7 | `tests/core/test_complete_mcp.py` | mock provider 回傳 tool_calls 再回文字 |
| 8 | 文件 | [mcp.md](./mcp.md)、[aicentral.md](./aicentral.md) 連結本規格 |

---

## 消費方範例規劃（aicentral-chat）

**新檔** `aicentral-chat/chat_mcp.py`（示範，非 aicentral 本體）：

```python
#!/usr/bin/env python3
"""終端對話：complete + MCP tool loop（v0.6.0）。"""

from aicentral import Chat

from chat_common import require_aicentral_config, resolved_model, run_chat_loop


def main() -> None:
    require_aicentral_config()
    model = resolved_model()
    chat = Chat(model=model, mcp_servers=["deepwiki"], max_tool_rounds=5)
    run_chat_loop(
        model=model,
        via="import Chat + MCP",
        stream_fn=lambda user_input: _sync_stream(chat, user_input),
    )


def _sync_stream(chat: Chat, user_input: str):
    # v0.6.0 若僅支援非串流 MCP loop，直接回傳 str 的迭代器包裝
    text = chat.complete(user_input)
    yield text


if __name__ == "__main__":
    main()
```

**手動三步（0.5.0 仍可用；0.6.0 後可簡化為一行 `complete`）**：

```python
from aicentral import MCPManager, complete

mgr = MCPManager.from_config()
openai_tools = mgr_to_openai(mgr.list_tools("deepwiki"))  # 0.6.0 內建轉換

messages = [{"role": "user", "content": "搜尋 aicentral"}]
r1 = complete(messages, tools=openai_tools, ...)  # 需 provider 回傳 tool_calls
# ... 應用層 call_tool、塞 role:tool、再 complete → 0.6.0 自動化此段
```

---

## 設定範例

**YAML**（沿用 0.5.0）或 **執行期註冊**（0.5.0+ 已支援，見 [mcp.md](./mcp.md)）：

```python
from aicentral import register_mcp_server, MCPManager

register_mcp_server("deepwiki", transport="http", url="https://mcp.deepwiki.com/mcp")
mgr = MCPManager.from_config()
```

`config/aicentral.yaml`：

```yaml
mcp_servers:
  deepwiki:
    transport: http
    url: https://mcp.deepwiki.com/mcp
    auth_type: none

mcp_settings:
  tool_name_prefix: true
  client_timeout: 30
  # allowed_servers: [deepwiki]
```

模型須支援 function calling（本機 Ollama 需選支援 tools 的模型；雲端 OpenAI 相容通常可）。

---

## 驗收標準

- [ ] `pip install -e ".[dev,mcp]"` + `pytest` 全過（含新測試）
- [ ] `complete(..., mcp_servers=["deepwiki"])` 在 mock 或整合環境完成 **一輪** list → tool_call → call → 最終文字
- [ ] `MCPError` 時不觸發 router fallback
- [ ] 未傳 `mcp_servers` 時行為與 **0.5.0** 一致
- [ ] [mcp.md](./mcp.md) 已更新「與 complete 的關係」為已實作
- [ ] （可選）`aicentral-chat/chat_mcp.py` 可手動跑通一輪對話

---

## 與其他文件

| 文件 | 關係 |
|------|------|
| [aicentral.md](./aicentral.md) | 路線圖總覽 |
| [mcp.md](./mcp.md) | Client 設定與 `MCPManager` |
| [aicentral-v0.6.1.md](./aicentral-v0.6.1.md) | Proxy HTTP（本版不做） |
| [aicentral-v4.0.md](./aicentral-v4.0.md) | MCP 分層歷史規格 |
