#!/usr/bin/env bash
# 本機開發一鍵設定：config/secret.yaml（若缺少）+ .venv + 可編輯安裝
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

if [[ ! -f config/secret.yaml ]]; then
  if [[ ! -f config/secret.yaml.example ]]; then
    echo "error: config/secret.yaml.example not found" >&2
    exit 1
  fi
  cp config/secret.yaml.example config/secret.yaml
  echo "Created config/secret.yaml — edit secrets and ensure Ollama is running (ollama pull gemma4:e2b)."
else
  echo "config/secret.yaml already exists — skipping."
fi

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
  echo "Created virtual environment at .venv"
fi

# shellcheck source=/dev/null
source .venv/bin/activate
pip install --upgrade pip

if command -v uv &>/dev/null; then
  uv pip install -e ".[dev]"
else
  pip install -e ".[dev]"
fi

echo ""
echo "Done. Activate with:  source .venv/bin/activate"
