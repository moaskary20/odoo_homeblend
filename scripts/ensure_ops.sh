#!/bin/bash
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
./venv/bin/python ./odoo/odoo-bin shell -c config/odoo.conf -d homeblend --no-http <<'PY'
from odoo.addons.homeblend_base.hooks import ensure_ops
ensure_ops(env)
env.cr.commit()
print('OPS_OK')
PY
