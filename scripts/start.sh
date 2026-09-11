#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if ss -tln | grep -q ':8069'; then
  echo "Odoo is already running on port 8069"
  exit 0
fi
mkdir -p "$ROOT/logs"
nohup "$ROOT/venv/bin/python" "$ROOT/odoo/odoo-bin" -c "$ROOT/config/odoo.conf" >> "$ROOT/logs/odoo-stdout.log" 2>&1 &
echo $! > "$ROOT/logs/odoo.pid"
echo "Odoo 19 started (PID $(cat "$ROOT/logs/odoo.pid")) — http://localhost:8069"
