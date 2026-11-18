#!/bin/sh
# Run hourly from cron. Requires the server .env and a reachable local app.
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
. "$SCRIPT_DIR/.env"
curl --fail --silent --show-error -u "$ADMIN_USERNAME:$ADMIN_PASSWORD" \
  -X POST http://127.0.0.1:8000/api/admin/reminders/run
