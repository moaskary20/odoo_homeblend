#!/bin/bash
# تحديث المشروع من GitHub ثم ترقية الموديولات وإعادة التشغيل عبر systemd إن وُجد.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
git fetch origin
git pull --ff-only origin main
if systemctl is-active --quiet odoo-homeblend 2>/dev/null; then
  sudo -n systemctl stop odoo-homeblend || true
  ./venv/bin/python ./odoo/odoo-bin -c config/odoo.conf -d homeblend \
    -u homeblend_base,homeblend_tenant,homeblend_fulfillment,artcasa_operations,homeblend_dms,homeblend_reports,homeblend_fonts \
    --stop-after-init
  sudo -n systemctl start odoo-homeblend
  echo "UPDATED_AND_RESTARTED"
else
  echo "PULLED: restart Odoo manually (systemctl start odoo-homeblend or ./scripts/start.sh)"
fi
