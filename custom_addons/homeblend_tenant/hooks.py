from odoo.addons.homeblend_base.hooks import ensure_ops


def post_init_hook(env):
    ensure_ops(env)
