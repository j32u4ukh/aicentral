# 日誌（logging）

aicentral 與 aicentral-agent 採用 Python 標準 **library logging** 慣例：

| 情境 | 行為 |
|------|------|
| `import aicentral` | 對 `aicentral` logger 掛 `NullHandler`、`propagate=False`，預設不輸出 |
| CLI / Gateway / 示範腳本 | 入口呼叫 `configure_logging()` |
| 函式庫內部 | `logging.getLogger(__name__)`，不直接 `print` |

## 應用程式入口

```python
import logging
from aicentral import configure_logging

configure_logging(level=logging.INFO, logger_names=["aicentral.history"])
```

aicentral-agent：

```python
from aicentral_agent import configure_logging

configure_logging(level=logging.INFO)
```

## 自訂輸出（檔案、JSON 等）

不依賴 `configure_logging`，自行設定 root 或 `aicentral` logger 的 Handler，並將套件 logger 的 `propagate` 設為 `True`：

```python
import logging

handler = logging.FileHandler("app.log", encoding="utf-8")
logging.getLogger().addHandler(handler)
logging.getLogger().setLevel(logging.INFO)

pkg = logging.getLogger("aicentral")
pkg.propagate = True
pkg.setLevel(logging.INFO)
```

## 開發除錯（dev 模式）

`aicentral.core.dev` 的 `dev_print` 僅在 `aicentral.yaml` → `aicentral_settings.dev: true` 時寫 stderr，與正式日誌分離。
