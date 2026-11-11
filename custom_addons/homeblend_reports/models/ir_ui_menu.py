from odoo import api, models


class IrUiMenu(models.Model):
    _inherit = "ir.ui.menu"

    @api.model
    def hb_deactivate_duplicate_accounting_menus(self):
        """إخفاء قوائم مكررة إن وُجدت، دون إنشاء سجلات ناقصة."""
        xmlids = [
            "homeblend_reports.menu_hb_app_add_customer",
            "homeblend_reports.menu_hb_app_add_supplier",
            "homeblend_reports.menu_hb_app_moves",
            "homeblend_reports.menu_hb_acct_trial",
            "homeblend_reports.menu_hb_acct_income",
            "homeblend_reports.menu_hb_acct_balance",
            "homeblend_reports.menu_hb_acct_financial",
        ]
        for xmlid in xmlids:
            menu = self.env.ref(xmlid, raise_if_not_found=False)
            if menu and menu.active:
                menu.active = False
        return True
