# aicentral

以 [BerriAI/litellm](https://github.com/BerriAI/litellm) 與 [jxnl/instructor](https://github.com/jxnl/instructor) 為核心的 Python 服務專案。

- **LiteLLM**：統一呼叫多家 LLM 供應商，可作為 proxy / 路由層。
- **Instructor**：在 LLM 回應上套用 Pydantic，取得型別安全的結構化輸出。

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
| `[project]` | 套件名稱、版本、說明、**執行期依賴**（litellm、instructor、pydantic 等） |
| `[project.optional-dependencies]` | 可選依賴群組；`dev` 含 pytest、ruff、mypy 等開發工具 |
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

### `src/aicentral/` — 應用程式套件

採用 **src layout**：原始碼放在 `src/` 下，避免測試時誤載入專案根目錄的同名模組。`__init__.py` 定義套件版本與對外介面，業務邏輯應集中在此目錄。

### `tests/` — 測試

使用 **pytest**。測試檔命名建議 `test_*.py`；執行時會自動把 `src` 加入路徑（由 `pyproject.toml` 的 `[tool.pytest.ini_options]` 設定）。

### `.env.example` / `.env`

- **`.env.example`**：可提交至版控的環境變數**範本**（不含真實金鑰）。
- **`.env`**：本機實際設定，由 `scripts/setup_env.ps1` 從範本複製產生；**勿提交**（已在 `.gitignore`）。

內含 API 金鑰、LiteLLM proxy 位址、日誌等級等；應用程式透過 `python-dotenv` 載入。

### `scripts/` — 開發輔助腳本

| 腳本 | 用途 |
|------|------|
| `setup_env.ps1` / `setup_env.sh` | 若尚無 `.env`，從 `.env.example` 建立 |
| `install_dev.ps1` / `install_dev.sh` | 建立 `.venv` 並以可編輯模式安裝專案與 `dev` 依賴 |

詳見 `scripts/README.md`。

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
.\scripts\setup_env.ps1       # 建立 .env（若尚未存在）
.\scripts\install_dev.ps1     # 建立虛擬環境並安裝依賴
.\.venv\Scripts\Activate.ps1
pytest
```

容器化開發請參考 `docker/README.md`。
