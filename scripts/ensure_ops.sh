#!/bin/bash
set -e
cd /media/mohamed/d1/odoohomeblend
./venv/bin/python ./odoo/odoo-bin shell -c config/odoo.conf -d homeblend --no-http <<'PY'
from odoo.addons.homeblend_base.hooks import ensure_ops
ensure_ops(env)
env.cr.commit()
print('OPS_OK')
PY
