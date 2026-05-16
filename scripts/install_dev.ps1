# Create .venv and install project with dev dependencies.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$Venv = Join-Path $Root ".venv"
if (-not (Test-Path $Venv)) {
    python -m venv $Venv
    Write-Host "Created virtual environment at $Venv"
}

$Python = Join-Path $Venv "Scripts\python.exe"
$Pip = Join-Path $Venv "Scripts\pip.exe"

& $Pip install --upgrade pip
if (Get-Command uv -ErrorAction SilentlyContinue) {
    & uv pip install -e ".[dev]"
} else {
    & $Pip install -e ".[dev]"
}

Write-Host ""
Write-Host "Done. Activate with:  .\.venv\Scripts\Activate.ps1"
