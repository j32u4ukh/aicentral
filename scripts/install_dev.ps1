# 本機開發一鍵設定：.env（若缺少）+ .venv + 可編輯安裝
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$Example = Join-Path $Root ".env.example"
$EnvFile = Join-Path $Root ".env"
if (-not (Test-Path $EnvFile)) {
    if (-not (Test-Path $Example)) {
        Write-Error ".env.example not found at $Example"
    }
    Copy-Item $Example $EnvFile
    Write-Host "Created .env from .env.example — ensure Ollama is running and OLLAMA_MODEL is pulled."
} else {
    Write-Host ".env already exists — skipping."
}

$Venv = Join-Path $Root ".venv"
if (-not (Test-Path $Venv)) {
    python -m venv $Venv
    Write-Host "Created virtual environment at $Venv"
}

$Pip = Join-Path $Venv "Scripts\pip.exe"
& $Pip install --upgrade pip
if (Get-Command uv -ErrorAction SilentlyContinue) {
    & uv pip install -e ".[dev]"
} else {
    & $Pip install -e ".[dev]"
}

Write-Host ""
Write-Host "Done. Activate with:  .\.venv\Scripts\Activate.ps1"
