# 開發腳本（scripts）

## 是否有必要？

| 項目 | 結論 |
|------|------|
| **整個 `scripts/` 目錄** | **非必要**，但建議保留 |
| **手動替代** | 下列指令即可完成相同流程，腳本僅為 convenience |

```powershell
# Windows — 與 install_dev.ps1 等價
Copy-Item config\secret.yaml.example config\secret.yaml -ErrorAction SilentlyContinue
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

```bash
# Unix — 與 install_dev.sh 等價
cp -n config/secret.yaml.example config/secret.yaml 2>/dev/null || true
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

| 腳本 | 評估 | 說明 |
|------|------|------|
| `install_dev.ps1` / `install_dev.sh` | **建議保留** | 一次完成 `config/secret.yaml`、虛擬環境、可編輯安裝；Windows / Unix 各一支 |

**原則**：腳本不是執行期依賴，不影響 `aicentral` 函式庫本身；新成員可選用腳本或照上方手動步驟操作。

---

## 腳本說明

| 腳本 | 用途 |
|------|------|
| `install_dev.ps1` | Windows：建立 `config/secret.yaml`（若尚無）→ 建立 `.venv` → `pip install -e ".[dev]"` |
| `install_dev.sh` | Unix/macOS：同上 |

若已安裝 [uv](https://github.com/astral-sh/uv)，腳本會優先使用 `uv pip install`。

---

## 快速開始

**Windows（PowerShell）：**

```powershell
.\scripts\install_dev.ps1
.\.venv\Scripts\Activate.ps1
pytest
```

**Unix / macOS：**

```bash
chmod +x scripts/install_dev.sh
./scripts/install_dev.sh
source .venv/bin/activate
pytest
```

安裝完成後請確認 Ollama 已運行，並編輯 `config/secret.yaml` 的 `ollama.model`（須已 `ollama pull`）。
