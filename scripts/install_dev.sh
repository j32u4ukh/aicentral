#!/usr/bin/env bash
# Create .venv and install project with dev dependencies.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

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
