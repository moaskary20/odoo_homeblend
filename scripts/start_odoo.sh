#!/bin/bash
set -e
cd /media/mohamed/d1/odoohomeblend
nohup ./venv/bin/python ./odoo/odoo-bin -c config/odoo.conf >> logs/odoo-stdout.log 2>&1 &
echo $! > logs/odoo.pid
echo STARTED:$(cat logs/odoo.pid)
