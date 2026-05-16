# 安全規劃

> 參考：[LiteLLM Proxy 認證與管控](https://docs.litellm.ai/docs/proxy/virtual_keys)、[litellm.md](./litellm.md)  
> 適用時機：**aicentral 對外提供 HTTP Gateway**（規劃於 v0.5），或本機服務暴露至區網／公網時。

---

## 背景與威脅模型

aicentral 預設為**函式庫**（`import` + 本機 Ollama），此時攻擊面小。  
一旦在本地或內網**開放 API 供外部調用**，且缺少雲端 WAF、API Gateway 等既有防護，可能面臨：

| 威脅 | 說明 |
|------|------|
| **未授權呼叫** | 掃描開放 port、濫用 `/v1/chat/completions` |
| **爬蟲／機器人** | 高頻請求耗盡 CPU、拖垮 Ollama |
| **金鑰外洩** | 設定檔、日誌、錯誤訊息洩漏後被重放 |
| **資源耗盡** | 超大 `messages`、長連線、無限重試 |
| **資料外洩** | 請求內容寫入日誌、被第三方 guardrail 送出 |

本文件規劃 **aicentral 輕量版** 防護，思想對齊 LiteLLM Proxy，但**不**照搬其 DB、Admin UI、数十种 guardrail 整合。

---

## 與 LiteLLM 的對照（我們要什麼、不要什麼）

| LiteLLM 能力 | 用途 | aicentral 規劃 |
|--------------|------|----------------|
| `master_key` | 管理端與強制全站認證 | ✅ **S1**：環境變數 `AICENTRAL_MASTER_KEY` |
| Virtual Keys（虛擬金鑰） | 每客戶端／每應用一把 API Key，可撤銷 | ✅ **S2**：金鑰表（先檔案/ env，後可選 DB） |
| `user_api_key_auth` | 每請求驗證 `Authorization: Bearer` | ✅ **S1**：Gateway 中介層 |
| RPM / TPM 限流 | 防爬蟲、控成本 | ✅ **S2**：記憶體或 Redis 滑動窗口 |
| `max_budget` / spend | 用量上限 | ⏳ **S3**：依 token 估算（本機 Ollama 可選） |
| `allowed_ips` | 僅允許指定 IP | ✅ **S2**：CIDR 白名單 |
| Guardrails | 輸入/輸出內容策略 | ⏳ **S4**：精簡 hook 介面，不內建十幾家廠商 |
| JWT / OAuth / SSO | 企業登入、Admin UI | ❌ 第一階段不做 |
| Prisma + 完整後台 | 金鑰/團隊/報表 UI | ❌ 不做；必要時僅 REST 管理 API |
| Team / Org 多租戶 | 複雜權限 | ⏳ **S4+** 若有需求再簡化實作 |

LiteLLM 明確指出：**未設定 `master_key` 屬於部署 misconfiguration**，不視為框架漏洞。aicentral 亦採 **預設必須設定金鑰才允許對外 bind**（fail-closed）。

---

## 分層防護（建議順序）

```
外部請求
  │
  ▼
[網路層] 僅內網 / 反向代理 TLS / IP 白名單
  │
  ▼
[邊界層] API Key 驗證、公開路由隔離
  │
  ▼
[速率層] 全局限流 + 每 Key 限流
  │
  ▼
[應用層] 請求大小、model 白名單、逾時
  │
  ▼
[內容層] 可選 guardrail hook
  │
  ▼
aicentral.complete() → Ollama / 雲端
```

---

## 實作階段（對齊 aicentral 版本）

### 現況（v0.1～v0.4，僅函式庫）

| 措施 | 說明 |
|------|------|
| Ollama 僅本機 | `OLLAMA_BASE_URL=http://127.0.0.1:11434`，勿對 `0.0.0.0` 暴露無防護 API |
| 不提交 `.env` | 金鑰僅環境變數；見 `.gitignore` |
| 消費方責任 | `aicentral-chat` 等勿把金鑰寫進前端 |

此階段**尚無** Gateway，本文 S1～S4 為**預先設計**，實作隨 v0.5 展開。

---

### S1 — Gateway 最小安全（建議併入 v0.5 第一個可對外版本）

**目標**：沒有金鑰就打不進來；預設不對公網裸奔。

| 項目 | 規格 |
|------|------|
| **Master Key** | `AICENTRAL_MASTER_KEY` 必填；`Authorization: Bearer <key>` |
| **公開路由** | 僅 `/health`（可選）；`/v1/chat/completions` 必須認證 |
| **預設監聽** | `127.0.0.1`；對外需明確設定 `AICENTRAL_HOST=0.0.0.0` 並搭配 S2 |
| **錯誤回應** | 401 不區分「金鑰錯」與「未帶金鑰」（防枚舉） |
| **模組位置** | `gateway/auth.py` |

參考 LiteLLM：`general_settings.master_key` + `user_api_key_auth` 依賴注入。

```yaml
# 概念設定（未來 config.yaml）
gateway:
  master_key: ${AICENTRAL_MASTER_KEY}
  bind: 127.0.0.1:8080
```

---

### S2 — 防爬蟲與濫用（v0.5+ 或 v0.5.1）

**目標**：就算金鑰洩漏，也難以瞬間打爆服務。

| 項目 | 規格 | LiteLLM 對照 |
|------|------|----------------|
| **Virtual Keys** | 多把客戶端金鑰，可個別停用；格式 `sk-ac-...` | Virtual Keys |
| **全局限流** | 例如 60 RPM / IP（無 Key 時仍擋在認證前） | 全域 + dynamic rate limiter |
| **每 Key 限流** | `rpm_limit`、`tpm_limit`（可選） | key metadata |
| **IP 白名單** | `allowed_ips` / CIDR | `general_settings.allowed_ips` |
| **請求上限** | `max_messages`、單則 `max_content_chars`、body size | 自訂（LiteLLM 部分端點有類似檢查） |
| **模組位置** | `gateway/rate_limit.py`、`gateway/keys.py` | hooks / auth_checks |

建議對**未帶 Key 的 IP** 做嚴格限流（如 5 req/min），減少掃 port 與爬蟲試探。

---

### S3 — 成本與權限（v0.6 或按需）

| 項目 | 規格 |
|------|------|
| **Model 白名單** | 每 Key 僅能呼叫允許的 model（防改用昂貴雲端模型） |
| **Budget** | 每 Key 每日請求次數或估算 token 上限 | 
| **管理 API** | 用 Master Key 建立/撤銷 Virtual Key（無完整 UI） |
| **稽核日誌** | 記錄 key_id、IP、model、延遲；**不**記錄完整 prompt（可配置） |

---

### S4 — 內容與進階（可選）

| 項目 | 規格 |
|------|------|
| **Guardrail Hook** | 單一介面：請求前/回應後檢查，可插自訂規則或外掛 | LiteLLM `guardrails` 精簡版 |
| **敏感詞 / 長度** | 內建最簡策略，不依賴第三方 SaaS |
| **Fail-closed** | 安全檢查服務掛掉時預設拒絕（可設定 fail-open 僅 dev） |

---

## 網路與部署建議（本地／內網）

即使實作 S1～S2，仍建議：

| 做法 | 說明 |
|------|------|
| **反向代理** | Nginx / Caddy：TLS、額外 rate limit、WAF 規則 |
| **僅內網 VPN** | Gateway 不直接暴露公網 |
| **mTLS** | 零信任內網可選 |
| **防火牆** | 只開放 proxy port 給已知來源 |

Ollama 預設 `11434` **不應**對外；對外只暴露 aicentral Gateway，由 Gateway 轉打本機 Ollama。

---

## 秘密與設定管理

| 規則 | 說明 |
|------|------|
| Master Key | 僅 env 或秘密管理器；長度 ≥ 32、隨機 |
| Virtual Keys | 可輪替；洩漏即廢止單 Key，不必換 Master |
| 日誌 | 禁止記錄 Bearer token、完整 API Key |
| 錯誤訊息 | 不向客戶端回傳 stack trace |
| 依賴掃描 | CI 可選 `pip audit` / Dependabot |

---

## 威脅與緩解對照表

| 情境 | 緩解 |
|------|------|
| 掃描器發現開放 API | S1 強制 Bearer；S2 IP + 全局限流 |
| 金鑰在 GitHub 外洩 | 單 Key 撤銷（S2）；rotate；`.env` 不進版控 |
| 單一爬蟲狂打 | S2 RPM/TPM；proxy 層 limit_req |
| 超大 payload 拖垮 Ollama | S2 body / message 上限；逾時 |
| 內網任意機器濫用 | S2 `allowed_ips`；VPN |
| 惡意 prompt 注入業務 | S4 guardrail；消費方自行過濾 |

---

## 模組規劃（`gateway/` 內）

```
gateway/
├── auth.py           # S1：Bearer、master / virtual key 驗證
├── keys.py           # S2：金鑰儲存與查詢（檔案 → 可選 DB）
├── rate_limit.py     # S2：IP / Key 限流
├── middleware.py     # 請求 ID、大小檢查、逾時
├── routes/           # 受保護的 OpenAI 相容路由
└── audit.py          # S3：稽核日誌（可選）
```

**依賴方向**：middleware → auth → rate_limit → routes → `core.complete()`  
安全邏輯**不得**散落在 `providers/` 或 `complete()` 內，避免函式庫直連時繞過 Gateway。

---

## 驗收清單（Gateway 上線前）

- [ ] 未帶 `Authorization` 之 `POST /v1/chat/completions` 回 **401**
- [ ] 錯誤金鑰回 **401**（訊息不洩漏是否存在該 Key）
- [ ] 預設僅監聽 `127.0.0.1`
- [ ] 全局限流生效（可用腳本壓測）
- [ ] Virtual Key 可停用後立即 401
- [ ] `allowed_ips` 外來源被拒絕（若啟用）
- [ ] 日誌不含完整金鑰與可識別個資的 prompt（依政策）
- [ ] Ollama 未直接暴露於公網

---

## 與其他文件的關係

| 文件 | 關係 |
|------|------|
| [aicentral.md](./aicentral.md) | v0.5 Gateway 功能邊界；本文為其安全子規格 |
| [concepts.md](./concepts.md) | `complete()` 語意；安全不改變函式庫 API |
| [litellm.md](./litellm.md) | 上游 Proxy 能力參考來源 |

---

## 小結

- **現在（函式庫階段）**：靠本機 Ollama + 不暴露 port + 管好 `.env`。  
- **未來（Gateway）**：對齊 LiteLLM 的 **認證 → 限流 → 權限 → 可選內容策略**，但保持輕量、可分期交付。  
- **第一個對外安全基線**：**S1（Master Key + 預設 localhost）**；防爬蟲重點在 **S2 限流與 IP 白名單**。

實作順序建議：**S1 與 Gateway 同期上線**，勿先開放無認證的 HTTP 再補洞。
