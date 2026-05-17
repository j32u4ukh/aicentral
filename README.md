# aicentral

提供給**其他專案**使用的 Python **AI 能力函式庫**（非業務服務）。設計上參考 [LiteLLM](https://github.com/BerriAI/litellm)（統一 LLM 路由）與 [Instructor](https://github.com/jxnl/instructor)（Pydantic 結構化輸出），並以輕量化實作**合併於本 repo**，**不依賴**上述兩個套件。

- 統一 `complete()` 呼叫 LLM（**v0.1 預設本機 Ollama**，OpenAI 相容協定）
- `complete_structured()` 回傳驗證過的 Pydantic model
- 可選 `[gateway]` 額外依賴，提供 OpenAI 相容 HTTP 介面

文件：[`docs/concepts.md`](docs/concepts.md)（核心概念）、[`docs/aicentral.md`](docs/aicentral.md)（架構與版本）、[`docs/aicentral-v0.1.md`](docs/aicentral-v0.1.md)（v0.1 實作紀錄）、[`docs/security.md`](docs/security.md)（Gateway 安全規劃）。

---

## 專案結構

```
aicentral/
├── .cursor/rules/          # Cursor AI 專案規則
├── docker/                 # 容器化部署與 LiteLLM 設定
├── scripts/                # 本機開發輔助腳本
├── src/aicentral/          # 應用程式原始碼（主套件）
├── tests/                  # 單元測試
├── .dockerignore           # Docker 建置時排除的檔案
├── .env.example            # 環境變數範本（複製為 .env 使用）
├── .python-version         # 建議使用的 Python 版本（3.11）
├── pyproject.toml          # 專案定義與工具設定（見下方說明）
└── README.md               # 本文件
```

---

## 主要檔案與目錄說明

### `pyproject.toml` — 專案的中樞設定檔

遵循 [PEP 621](https://peps.python.org/pep-0621/)，是現代 Python 專案**單一真相來源**，取代過去的 `setup.py` / `requirements.txt` 分散設定。在本專案中扮演以下角色：

| 區塊 | 用途 |
|------|------|
| `[project]` | 套件名稱、版本、**執行期依賴**（v0.1：`httpx`、`python-dotenv`；不含 litellm / instructor） |
| `[project.optional-dependencies]` | `gateway`（FastAPI）、`dev`（pytest、ruff、mypy） |
| `[build-system]` | 指定用 **hatchling** 將 `src/aicentral` 打包成可安裝的 wheel |
| `[tool.pytest.ini_options]` | pytest 預設：測試目錄 `tests/`、將 `src` 加入 `PYTHONPATH` |
| `[tool.ruff]` / `[tool.ruff.lint]` | 程式碼風格與靜態檢查（行寬、import 排序等） |
| `[tool.mypy]` | 型別檢查設定（strict 模式、檢查 `aicentral` 套件） |
| `[tool.uv]` | 若使用 [uv](https://github.com/astral-sh/uv) 管理環境，標記此目錄為可安裝套件 |

常見操作：

```powershell
pip install -e ".[dev]"   # 可編輯模式安裝專案 + 開發依賴
pytest                    # 執行測試（設定來自 pyproject.toml）
ruff check .              # 程式碼檢查
```

### `src/aicentral/` — 函式庫原始碼

採用 **src layout**。此目錄僅含 AI 能力（core、providers、routing、structured、可選 gateway），**不含**業務服務或領域 API；業務邏輯應在引用 `aicentral` 的專案中實作。

### `tests/` — 測試

使用 **pytest**。測試檔命名建議 `test_*.py`；執行時會自動把 `src` 加入路徑（由 `pyproject.toml` 的 `[tool.pytest.ini_options]` 設定）。

### `.env.example` / `.env`

- **`.env.example`**：可提交至版控的環境變數**範本**（不含真實金鑰）。
- **`.env`**：本機實際設定，可手動複製 `.env.example`，或由 `scripts/install_dev.*` 自動建立；**勿提交**（已在 `.gitignore`）。

內含 API 金鑰、LiteLLM proxy 位址、日誌等級等；應用程式透過 `python-dotenv` 載入。

### `scripts/` — 開發輔助腳本（可選）

| 腳本 | 用途 |
|------|------|
| `install_dev.ps1` / `install_dev.sh` | 建立 `.env`（若尚無）、`.venv`，並以可編輯模式安裝 `dev` 依賴 |

非必要，可改用手動 `pip install -e ".[dev]"`。評估說明見 `scripts/README.md`。

### `docker/` — 容器化

| 檔案 | 用途 |
|------|------|
| `Dockerfile` | 建置 aicentral 應用映像 |
| `docker-compose.yml` | 編排服務：PostgreSQL、可選 LiteLLM proxy、應用本身 |
| `litellm_config.yaml` | LiteLLM proxy 的模型與金鑰設定 |
| `.env.example` | Docker 環境專用變數範本（複製為 `docker/.env`） |

詳見 `docker/README.md`。

### `.cursor/rules/` — Cursor AI 規則

`.mdc` 檔案提供 AI 助手持續的專案脈絡，例如：

- `project-overview.mdc`：技術棧與目錄慣例（每次對話套用）
- `python-standards.mdc`：撰寫 Python 時的型別、環境變數、模組分工慣例

### 其他

| 檔案 | 用途 |
|------|------|
| `.python-version` | 供 pyenv / mise 等工具自動選用 Python 3.11 |
| `.dockerignore` | 縮小 Docker 建置上下文（排除 `.venv`、`.git` 等） |
| `.gitignore` | 版控排除清單（`.env`、`.venv`、`__pycache__` 等） |

---

## 快速開始

```powershell
.\scripts\install_dev.ps1     # 可選：.env + 虛擬環境 + 安裝依賴
.\.venv\Scripts\Activate.ps1
# 確認 Ollama 已啟動，並編輯 .env 的 OLLAMA_MODEL（預設 llama3.2）
pytest
```

容器化開發請參考 `docker/README.md`。
