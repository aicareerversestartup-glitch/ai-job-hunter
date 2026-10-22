#!/usr/bin/env bash
# One-time setup on macOS/Linux. Run from the project folder: bash scripts/setup.sh
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m playwright install chromium
if [ ! -f .env ]; then
  cp .env.example .env
  secret=$(.venv/bin/python -c "import secrets; print(secrets.token_urlsafe(48))")
  sed -i.bak "s|^SECRET_KEY=$|SECRET_KEY=${secret}|" .env && rm -f .env.bak
fi
(cd frontend && npm install --no-audit --no-fund)
.venv/bin/python -m alembic upgrade head
echo "Setup complete. Start with: bash scripts/dev.sh"
