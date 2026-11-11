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
    ("pl_cogs", "قائمة الدخل: تكلفة البضاعة المباعة"),
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
            self._hb_configure_inventory_accounting(company)
        return True

    @api.model
    def hb_configure_inventory_accounting(self):
        """تفعيل دورة البيع بمخزون سالب مع قيود التكلفة والتسوية."""
        companies = self.env["res.company"].search([("name", "ilike", "home"), ("name", "ilike", "blend")])
        for company in companies:
            self._hb_load_company_chart(company)
            self._hb_configure_inventory_accounting(company)
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

    def _hb_account(self, company, code):
        return self.env["account.account"].with_company(company).sudo().search(
            [("code", "=", code), ("company_ids", "in", company.id)],
            limit=1,
        )

    def _hb_stock_journal(self, company):
        Journal = self.env["account.journal"].with_company(company).sudo()
        journal = Journal.search([
            ("company_id", "=", company.id),
            ("code", "=", "STJ"),
        ], limit=1)
        if journal:
            return journal
        journal = Journal.search([
            ("company_id", "=", company.id),
            ("type", "=", "general"),
            ("name", "ilike", "مخزون"),
        ], limit=1)
        if journal:
            return journal
        return Journal.create({
            "name": "قيود المخزون",
            "code": "STJ",
            "type": "general",
            "company_id": company.id,
        })

    def _hb_configure_inventory_accounting(self, company):
        """تقييم دائم + Anglo-Saxon وربط فئات المنتجات بحسابات HB."""
        if "inventory_valuation" not in company._fields:
            return False

        stock_account = self._hb_account(company, "HB12012")
        income_account = self._hb_account(company, "HB42001")
        cogs_account = self._hb_account(company, "HB31000")
        price_diff_account = self._hb_account(company, "HB31019")
        variation_account = self._hb_account(company, "HB31020")
        if not (stock_account and income_account and cogs_account and price_diff_account):
            return False

        journal = self._hb_stock_journal(company)
        company.sudo().write({
            "anglo_saxon_accounting": True,
            "inventory_valuation": "real_time",
            "cost_method": "average",
            "inventory_period": "manual",
            "account_stock_valuation_id": stock_account.id,
            "account_stock_journal_id": journal.id,
        })

        stock_vals = {}
        if "account_stock_expense_id" in stock_account._fields:
            stock_vals["account_stock_expense_id"] = cogs_account.id
        if "account_stock_variation_id" in stock_account._fields and variation_account:
            stock_vals["account_stock_variation_id"] = variation_account.id
        if stock_vals:
            stock_account.sudo().write(stock_vals)

        Category = self.env["product.category"].with_company(company).sudo()
        categories = Category.search([])
        for categ in categories:
            # غيّر طريقة التكلفة فقط عند الحاجة؛ تغييرها يطلق إعادة تقييم كل المنتجات
            vals = {
                "property_valuation": "real_time",
                "property_stock_valuation_account_id": stock_account.id,
                "property_stock_journal": journal.id,
                "property_account_income_categ_id": income_account.id,
                "property_account_expense_categ_id": cogs_account.id,
            }
            if "property_price_difference_account_id" in categ._fields:
                vals["property_price_difference_account_id"] = price_diff_account.id
            if categ.property_cost_method != "average":
                vals["property_cost_method"] = "average"
            categ.with_context(tracking_disable=True).write(vals)

        # الإعداد الافتراضي للفئات الجديدة
        IrDefault = self.env["ir.default"].sudo()
        defaults = {
            "property_valuation": "real_time",
            "property_cost_method": "average",
            "property_stock_valuation_account_id": stock_account.id,
            "property_stock_journal": journal.id,
            "property_account_income_categ_id": income_account.id,
            "property_account_expense_categ_id": cogs_account.id,
            "property_price_difference_account_id": price_diff_account.id,
        }
        for field_name, value in defaults.items():
            if field_name not in Category._fields:
                continue
            IrDefault.set("product.category", field_name, value, company_id=company.id)

        # السماح بالبيع/التسليم حتى مع رصيد صفر (مخزون سالب)
        self._hb_allow_negative_stock(company)
        return True

    def _hb_allow_negative_stock(self, company):
        """لا يمنع Odoo القياسي التسليم السالب؛ نؤكد إعدادات المستودع إن وُجدت."""
        Warehouse = self.env["stock.warehouse"].with_company(company).sudo()
        warehouses = Warehouse.search([("company_id", "=", company.id)])
        for warehouse in warehouses:
            picking_type = warehouse.out_type_id
            if picking_type and "reservation_method" in picking_type._fields:
                # at_confirm يحجز إن وُجد رصيد، وإلا يُسمح بالتحقق لاحقاً حتى لو سالب
                if picking_type.reservation_method == "manual":
                    picking_type.reservation_method = "at_confirm"
        return True
