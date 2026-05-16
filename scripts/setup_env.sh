#!/usr/bin/env bash
# Create .env from .env.example if it does not exist.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXAMPLE="${ROOT}/.env.example"
ENV_FILE="${ROOT}/.env"

if [[ ! -f "${EXAMPLE}" ]]; then
  echo "error: .env.example not found at ${EXAMPLE}" >&2
  exit 1
fi

if [[ -f "${ENV_FILE}" ]]; then
  echo ".env already exists — skipping."
  exit 0
fi

cp "${EXAMPLE}" "${ENV_FILE}"
echo "Created .env from .env.example. Edit ${ENV_FILE} and set your API keys."
