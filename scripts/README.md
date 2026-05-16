# Scripts

Utility scripts for local development setup.

| Script | Description |
|--------|-------------|
| `setup_env.ps1` | Create `.env` from `.env.example` (Windows PowerShell) |
| `setup_env.sh` | Create `.env` from `.env.example` (Unix/macOS) |
| `install_dev.ps1` | Create venv and install dev dependencies (Windows) |
| `install_dev.sh` | Create venv and install dev dependencies (Unix) |

## Quick start

**Windows (PowerShell):**

```powershell
.\scripts\setup_env.ps1
.\scripts\install_dev.ps1
```

**Unix:**

```bash
chmod +x scripts/*.sh
./scripts/setup_env.sh
./scripts/install_dev.sh
```
