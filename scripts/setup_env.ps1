# Create .env from .env.example if it does not exist.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Example = Join-Path $Root ".env.example"
$EnvFile = Join-Path $Root ".env"

if (-not (Test-Path $Example)) {
    Write-Error ".env.example not found at $Example"
}

if (Test-Path $EnvFile) {
    Write-Host ".env already exists — skipping."
    exit 0
}

Copy-Item $Example $EnvFile
Write-Host "Created .env from .env.example. Edit $EnvFile and set your API keys."
