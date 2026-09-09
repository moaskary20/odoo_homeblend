#!/bin/bash
set -euo pipefail
ROOT="/media/mohamed/d1/odoohomeblend"
if [[ -f "$ROOT/logs/odoo.pid" ]]; then
  PID=$(cat "$ROOT/logs/odoo.pid")
  if kill -0 "$PID" 2>/dev/null; then
    kill "$PID"
    echo "Stopped Odoo PID $PID"
  fi
  rm -f "$ROOT/logs/odoo.pid"
fi
pkill -f "$ROOT/odoo/odoo-bin" 2>/dev/null || true
echo "Odoo stopped"
