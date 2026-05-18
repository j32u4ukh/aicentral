# aicentral 文件索引

本目錄說明 **aicentral** 函式庫的架構、用法與設計決策。aicentral 是給其他 Python 專案 `import` 用的 **AI 能力層**（`complete()`、`complete_structured()`），不是獨立的聊天產品或業務後端。

---

## 建議閱讀順序

| 你是… | 建議路徑 |
|--------|----------|
| **第一次接觸** | [concepts.md](./concepts.md) → [aicentral.md](./aicentral.md) |
| **要接 Ollama / 改預設模型** | [routing.md](./routing.md)（`config/aicentral.yaml`、`config/secret.yaml`） |
| **要接 OpenAI / Claude / Gemini** | [routing.md](./routing.md) + [aicentral-v4.0.md](./aicentral-v4.0.md) |
| **結構化輸出（Pydantic）** | [concepts.md](./concepts.md) → [aicentral-v3.0.md](./aicentral-v3.0.md) |
| **MCP 工具** | [mcp.md](./mcp.md) |
| **MCP 工具編排（0.6.0）** | [aicentral-v0.6.0.md](./aicentral-v0.6.0.md) |
| **Proxy MCP HTTP（0.6.1 可選）** | [aicentral-v0.6.1.md](./aicentral-v0.6.1.md) |
| **本機 HTTP Proxy / Gateway（v5.0）** | [proxy.md](./proxy.md)（使用說明）· [aicentral-v5.0 .md](./aicentral-v5.0%20.md)（規格） |
| **未來對外開 HTTP API** | [security.md](./security.md) |
| **想了解設計從哪來** | [litellm.md](./litellm.md)、[instructor.md](./instructor.md) |

---

## 核心文件

### [aicentral.md](./aicentral.md) — 專案架構與路線圖

- 專案定位（library vs 消費方應用）
- **0.5.0** 已交付能力、**0.6.x** MCP MVP 規劃
- 刻意不做清單（OAuth、semantic filter 等保持輕量）
- **適合**：掌握全貌、查下一步該做什麼

### [concepts.md](./concepts.md) — 核心概念（白話）

- aicentral 與 `complete()` 在做什麼
- `messages`、串流、`Chat` 有/無狀態
- `complete_structured()` 與一般對話的差別
- **適合**：不熟 LLM API 的開發者入門

### [routing.md](./routing.md) — 模型選路（庫內 Router）

- **不是**後端 HTTP 接口；是程式內依 `model` 選 provider、金鑰、fallback
- `parse_model`、`effective_model`（未傳 model 時用誰）、`defaults.model`
- `config/aicentral.yaml` 別名、`router.fallbacks`（Ollama 失敗 → 雲端）
- **適合**：換模型、多供應商、除錯「為什麼還是走 Ollama」

### [mcp.md](./mcp.md) — MCP 工具層

- MCP 與 LLM provider 的分工（**不**放在 `providers/`）
- `mcp_servers` 設定、`MCPManager`、`pip install "aicentral[mcp]"`
- **適合**：連外部 MCP server（stdio / http / sse）

### [security.md](./security.md) — Gateway 安全規劃

- 對外暴露 API 時的威脅模型（未授權、爬蟲、金鑰外洩等）
- 對照 LiteLLM Proxy 的 Master Key、限流、白名單等分階段規劃（S1～S4）
- **適合**：規劃 v5.0 HTTP Gateway，**與日常本機 `import` 無關**

---

## 版本規格（實作紀錄）

| 文件 | 狀態 | 摘要 |
|------|------|------|
| [aicentral-v1.0.md](./aicentral-v1.0.md) | 已完成 | 首版：`complete()` + Ollama |
| [aicentral-v1.1.md](./aicentral-v1.1.md) | 已完成 | `Chat`、串流、歷史策略 |
| [aicentral-v2.0.md](./aicentral-v2.0.md) | 已完成 | `core/`、`routing/parser`、`providers` |
| [aicentral-v3.0.md](./aicentral-v3.0.md) | 已完成 | `complete_structured()`、重試由消費方負責 |
| [aicentral-v4.0.md](./aicentral-v4.0.md) | 規劃／部分實作 | 多 provider、yaml config、MCP、fallback |
| [aicentral-v5.0 .md](./aicentral-v5.0%20.md) | 規劃／部分實作 | 本機 HTTP Gateway（OpenAI 相容） |

總覽以 [aicentral.md](./aicentral.md) 為準；各版細節以對應 `aicentral-v*.md` 為準。

---

## 設計參考（上游專案，非執行期依賴）

### [litellm.md](./litellm.md) — LiteLLM 概述

- 統一 `model="provider/..."`、Proxy Gateway、100+ provider
- aicentral **不安裝** litellm；只參考其 `llms/*`、`proxy` 設計
- **適合**：理解 v4 routing、config、MCP 分層為何這樣切

### [instructor.md](./instructor.md) — Instructor 概述

- Pydantic 結構化輸出、驗證與重試思想
- aicentral v3 的 `complete_structured()` 為 **Instructor-lite**（自建 `structured/`）
- **適合**：理解結構化 API 與 `append_retry_hint` 的取捨

---

## 程式與設定快速連結

| 資源 | 路徑 |
|------|------|
| 套件原始碼 | `../src/aicentral/` |
| yaml 主設定 | [../config/aicentral.yaml](../config/aicentral.yaml) |
| 機密範例 | [../config/secret.yaml.example](../config/secret.yaml.example) |
| 終端對話範例 | [../../aicentral-chat](../../aicentral-chat) |
| 結構化範例 | [../../aicentral-structured-demo](../../aicentral-structured-demo) |

---

## 名詞對照（避免混淆）

| 名詞 | 意思 |
|------|------|
| **routing / Router** | 庫內 `model` → provider 選路（見 [routing.md](./routing.md)） |
| **provider** | OpenAI 相容 / Anthropic / Gemini 等 LLM 適配器（`providers/`） |
| **Gateway** | 未來對外的 HTTP 服務（v5.0），不是現在的 routing |
| **MCP** | 外部工具協定（`mcp/`），不是 LLM |
