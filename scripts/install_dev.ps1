# 本機開發一鍵設定：config/secret.yaml（若缺少）+ .venv + 可編輯安裝
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$SecretExample = Join-Path $Root "config\secret.yaml.example"
$SecretFile = Join-Path $Root "config\secret.yaml"
if (-not (Test-Path $SecretFile)) {
    if (-not (Test-Path $SecretExample)) {
        Write-Error "config/secret.yaml.example not found at $SecretExample"
    }
    Copy-Item $SecretExample $SecretFile
    Write-Host "Created config/secret.yaml — edit secrets and ensure Ollama is running (ollama pull gemma4:e2b)."
} else {
    Write-Host "config/secret.yaml already exists — skipping."
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
