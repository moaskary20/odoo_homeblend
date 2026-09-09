def post_init_hook(env):
    """تحويل خط المستندات في الشركات القائمة إلى Tajawal."""
    env["res.company"].sudo().search([("font", "!=", "Tajawal")]).write({"font": "Tajawal"})
