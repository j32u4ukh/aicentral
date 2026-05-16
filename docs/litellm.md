# LiteLLM 框架概述

> 上游專案：[BerriAI/litellm](https://github.com/BerriAI/litellm)  
> 官方文件：<https://docs.litellm.ai>

## 是什麼

LiteLLM 是開源的 **AI Gateway**，用**統一的 OpenAI 相容介面**呼叫 100+ 家 LLM 供應商（OpenAI、Anthropic、Gemini、Bedrock、Azure 等），不必為每家廠商維護不同的 SDK 與請求格式。

## 兩種使用方式

| 模式 | 說明 | 典型場景 |
|------|------|----------|
| **Python SDK** | 在程式中 `import litellm`，直接呼叫 `completion()` 等函式 | 應用內嵌、腳本、單體服務 |
| **Proxy Server（AI Gateway）** | 部署 `litellm` 代理服務，對外提供 OpenAI 格式 HTTP API | 團隊共用、金鑰管理、流量控管、可觀測性 |

兩者底層共用同一套 provider 轉換邏輯；aicentral 若需集中管理金鑰與路由，通常會採 Proxy 模式。

## 核心能力（簡述）

- **統一 API**：`model="openai/gpt-4o"`、`model="anthropic/claude-..."` 等字串即可切換供應商
- **OpenAI 相容**：現有使用 OpenAI SDK 的程式，多半只需改 `base_url` 即可接上 Proxy
- **Gateway 功能**（Proxy）：虛擬金鑰、用量追蹤、guardrails、負載平衡、管理後台
- **多種端點**：chat、embeddings、images、audio、batches、rerank 等（依供應商支援而定）

## 程式庫目錄結構（`litellm/litellm/`）

```
litellm/
├── llms/               # 各供應商的請求/回應轉換（最大的一塊）
├── proxy/              # AI Gateway 服務（FastAPI、管理端點、guardrails）
├── router_strategy/    # 路由策略（fallback、負載、adaptive 等）
├── integrations/       # 與外部系統整合（日誌、追蹤、快取等）
├── litellm_core_utils/ # 共用工具、重試、串流處理
├── types/              # 型別定義
├── caching/            # 快取
├── rag/                # RAG 相關（較新功能）
└── ...                 # embeddings、images、evals 等功能模組
```

**閱讀建議**：先理解 `completion()` 如何依 `model` 字串分派到 `llms/` 下對應 provider；若做 Gateway，再讀 `proxy/` 與設定檔（如 `config.yaml`）。

## 與 aicentral 的關係

- aicentral **參考** LiteLLM 設計，在 `providers/`、`routing/` 內自行實作，**不安裝** `litellm` 套件。
- 其他專案 `pip install aicentral` 後使用 `complete()`，無需直接依賴 LiteLLM。
- `docker/` 內 LiteLLM 設定僅供本機對照／過渡，非執行期必要依賴。

## 最小範例

```python
from litellm import completion

response = completion(
    model="openai/gpt-4o-mini",
    messages=[{"role": "user", "content": "Hello"}],
)
print(response.choices[0].message.content)
```

```bash
# Proxy 模式（簡化）
litellm --model gpt-4o
# 之後以 OpenAI SDK 連 http://localhost:4000
```
