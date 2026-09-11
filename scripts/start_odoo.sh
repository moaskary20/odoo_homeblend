#!/bin/bash
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p logs
nohup ./venv/bin/python ./odoo/odoo-bin -c config/odoo.conf >> logs/odoo-stdout.log 2>&1 &
echo $! > logs/odoo.pid
echo STARTED:$(cat logs/odoo.pid)
