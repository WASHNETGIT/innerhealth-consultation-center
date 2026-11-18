#!/usr/bin/env bash
# Bootstrap and run the Inner Health scan booking/admin app locally.
set -euo pipefail
APP_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
cd "$APP_DIR"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is required. Install Python 3.11+ and run this script again." >&2
  exit 1
fi
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi
. .venv/bin/activate
if ! python -c "import fastapi, uvicorn, sqlalchemy, pydantic" 2>/dev/null; then
  python -m pip install -r requirements.txt
fi
if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example. Add account holder name and branch code for EFT instructions."
fi

read -r -p "Admin username [admin]: " ADMIN_USER
ADMIN_USER="${ADMIN_USER:-admin}"
read -r -s -p "Admin password: " ADMIN_PASS
printf '\n'
if [ -z "$ADMIN_PASS" ]; then
  echo "Admin password cannot be empty." >&2
  exit 1
fi
export ADMIN_USERNAME="$ADMIN_USER"
export ADMIN_PASSWORD="$ADMIN_PASS"
PORT="${PORT:-8000}"
echo "Starting Inner Health Scan Center on http://localhost:${PORT}"
echo "Admin dashboard: http://localhost:${PORT}/admin/bookings"
echo "Public booking:   http://localhost:${PORT}/book"
exec python -m uvicorn main:app --host 0.0.0.0 --port "$PORT"
