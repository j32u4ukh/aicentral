#!/usr/bin/env bash
# 本機開發一鍵設定：.env（若缺少）+ .venv + 可編輯安裝
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

if [[ ! -f .env ]]; then
  if [[ ! -f .env.example ]]; then
    echo "error: .env.example not found" >&2
    exit 1
  fi
  cp .env.example .env
  echo "Created .env from .env.example — please set OPENAI_API_KEY."
else
  echo ".env already exists — skipping."
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
