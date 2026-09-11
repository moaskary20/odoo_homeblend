#!/bin/bash
# تحديث المشروع من GitHub ثم ترقية الموديولات وإعادة التشغيل عبر systemd إن وُجد.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [ "$(id -u)" -eq 0 ]; then
  OWNER="$(stat -c %U "$ROOT")"
  runuser -u "$OWNER" -- git -C "$ROOT" fetch origin
  runuser -u "$OWNER" -- git -C "$ROOT" pull --ff-only origin main
else
  git fetch origin
  git pull --ff-only origin main
fi
if systemctl is-active --quiet odoo-homeblend 2>/dev/null; then
  systemctl stop odoo-homeblend || true
  ./venv/bin/python ./odoo/odoo-bin -c config/odoo.conf -d homeblend \
    -u homeblend_base,homeblend_tenant,homeblend_fulfillment,artcasa_operations,homeblend_dms,homeblend_reports,homeblend_fonts \
    --stop-after-init
  systemctl start odoo-homeblend
  echo "UPDATED_AND_RESTARTED"
else
  echo "PULLED: restart Odoo with: systemctl start odoo-homeblend"
fi
