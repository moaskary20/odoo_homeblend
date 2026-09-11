#!/bin/bash
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PID=$(cat logs/odoo.pid 2>/dev/null || true)
if [ -n "$PID" ] && ps -p "$PID" >/dev/null 2>&1; then
  kill "$PID"
  for i in 1 2 3 4 5 6 7 8 9 10; do
    ps -p "$PID" >/dev/null 2>&1 || break
    sleep 1
  done
  ps -p "$PID" >/dev/null 2>&1 && kill -9 "$PID" || true
fi
./venv/bin/python ./odoo/odoo-bin -c config/odoo.conf -d homeblend \
  -u homeblend_base,homeblend_tenant,homeblend_fulfillment,artcasa_operations,homeblend_dms,homeblend_reports,homeblend_fonts \
  --stop-after-init
./scripts/ensure_ops.sh
nohup ./venv/bin/python ./odoo/odoo-bin -c config/odoo.conf >> logs/odoo-stdout.log 2>&1 &
echo $! > logs/odoo.pid
echo STARTED:$(cat logs/odoo.pid)
