#!/bin/bash
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
./venv/bin/python ./odoo/odoo-bin -c config/odoo.conf -d homeblend \
  -u homeblend_base,homeblend_tenant,homeblend_fulfillment,artcasa_operations,homeblend_reports \
  --stop-after-init
echo UPDATE_OK
