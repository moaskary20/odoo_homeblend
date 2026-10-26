from odoo import api, fields, models
from odoo.fields import Command

from .chart_data import ACCOUNTS, GROUPS

CREDIT_TYPES = {
    "liability_payable",
    "liability_credit_card",
    "liability_current",
    "liability_non_current",
    "equity",
    "equity_unaffected",
    "income",
    "income_other",
}

SECTION_SELECTION = [
    ("bs_cash", "الميزانية: نقدية بالبنوك والخزينة"),
    ("bs_receivable", "الميزانية: مدينون وأرصدة مدينة أخرى"),
    ("bs_related_asset", "الميزانية: شركات شقيقة مدينة"),
    ("bs_inventory", "الميزانية: المخازن"),
    ("bs_fixed", "الميزانية: أصول ثابتة"),
    ("bs_fixed_contra", "الميزانية: مخصص إهلاك الأصول"),
    ("bs_other_asset", "الميزانية: أصول أخرى"),
    ("bs_payable", "الميزانية: دائنون وأرصدة دائنة أخرى"),
    ("bs_related_liability", "الميزانية: شركات شقيقة دائنة"),
    ("bs_advances", "الميزانية: دفعات محصلة من الغير"),
    ("bs_provision", "الميزانية: مخصصات"),
    ("bs_statutory", "الميزانية: التزامات نظامية"),
    ("eq_capital", "الميزانية: رأس المال"),
    ("eq_retained", "الميزانية: أرباح وخسائر مرحلة"),
    ("eq_partner_buy", "الميزانية: جاري الشركاء شراء"),
    ("eq_partner_sell", "الميزانية: جاري الشركاء بيع"),
    ("pl_revenue_activity", "قائمة الدخل: إيرادات النشاط"),
    ("pl_cost_indirect", "قائمة الدخل: تكاليف عمليات غير مباشرة"),
    ("pl_cost_wages", "قائمة الدخل: أجور ومرتبات العمليات"),
    ("pl_cost_overhead", "قائمة الدخل: مصروفات عمومية للعمليات"),
    ("pl_cost_depr", "قائمة الدخل: إهلاكات العمليات"),
    ("pl_other_income", "قائمة الدخل: إيرادات متنوعة"),
    ("pl_bank_income", "قائمة الدخل: فوائد بنكية"),
    ("pl_marketing", "قائمة الدخل: مصاريف تسويقية"),
    ("pl_fx", "قائمة الدخل: فروق أسعار عملة"),
    ("pl_admin_wages", "قائمة الدخل: أجور ومرتبات إدارية"),
    ("pl_admin_leave", "قائمة الدخل: مخصصات إجازات ونهاية خدمة"),
    ("pl_admin_depr", "قائمة الدخل: إهلاكات إدارية"),
    ("pl_admin_general", "قائمة الدخل: مصاريف إدارية وعامة"),
    ("pl_admin_fees", "قائمة الدخل: أتعاب محاسبية وقانونية"),
]


class AccountAccount(models.Model):
    _inherit = "account.account"

    hb_chart = fields.Boolean(string="ضمن شجرة هوم بليند", index=True)
    hb_partner_id = fields.Many2one("res.partner", string="العميل أو المورد", index=True)
    hb_statement_section = fields.Selection(SECTION_SELECTION, string="بند القائمة المالية")
    hb_normal_balance = fields.Selection(
        [("debit", "مدين"), ("credit", "دائن")],
        string="الطبيعة",
        compute="_compute_hb_normal_balance",
        store=True,
    )

    @api.depends("account_type")
    def _compute_hb_normal_balance(self):
        for account in self:
            account.hb_normal_balance = "credit" if account.account_type in CREDIT_TYPES else "debit"

    @api.model
    def hb_load_homeblend_chart(self):
        companies = self.env["res.company"].search([("name", "ilike", "home"), ("name", "ilike", "blend")])
        for company in companies:
            self._hb_load_company_chart(company)
        return True

    def _hb_load_company_chart(self, company):
        Group = self.env["account.group"].sudo()
        root = company.root_id
        for prefix, name in GROUPS:
            group = Group.search([
                ("company_id", "=", root.id),
                ("code_prefix_start", "=", prefix),
                ("code_prefix_end", "=", prefix),
            ], limit=1)
            if group:
                if group.name != name:
                    group.name = name
                continue
            Group.create({
                "name": name,
                "code_prefix_start": prefix,
                "code_prefix_end": prefix,
                "company_id": root.id,
            })

        Account = self.env["account.account"].with_company(company).sudo()
        for code, name, account_type, section, reconcile in ACCOUNTS:
            account = Account.search([("code", "=", code)], limit=1)
            vals = {
                "name": name,
                "hb_chart": True,
                "hb_statement_section": section,
            }
            if account:
                account.write(vals)
                continue
            Account.create({
                **vals,
                "code": code,
                "account_type": account_type,
                "reconcile": reconcile,
                "company_ids": [Command.set([company.id])],
            })
        return True
