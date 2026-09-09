from odoo import api, fields, models, _


class HomeblendFinancialReportWizard(models.TransientModel):
    _name = "homeblend.financial.report.wizard"
    _description = "معالج القائمة المالية"

    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    date_from = fields.Date(string="من", required=True, default=lambda self: fields.Date.context_today(self).replace(month=1, day=1))
    date_to = fields.Date(string="إلى", required=True, default=fields.Date.context_today)
    report_type = fields.Selection(
        [("balance", "الميزانية العمومية"), ("pnl", "الأرباح والخسائر")],
        required=True,
        default="balance",
        string="نوع التقرير",
    )

    def action_print(self):
        self.ensure_one()
        return self.env.ref("homeblend_reports.action_report_financial_pdf").report_action(self)

    def get_report_data(self):
        self.ensure_one()
        return self._get_report_data()

    def _base_domain(self, period=True):
        """سطور قيود مرحّلة للشركة، مع تحديد الفترة أو حتى تاريخ التقرير."""
        self.ensure_one()
        domain = [
            ("parent_state", "=", "posted"),
            ("company_id", "=", self.company_id.id),
            ("display_type", "not in", ["line_section", "line_note"]),
        ]
        if period:
            domain += [("date", ">=", self.date_from), ("date", "<=", self.date_to)]
        else:
            domain += [("date", "<=", self.date_to)]
        return domain

    def _section_lines(self, account_types, sign=1):
        """أرصدة الحسابات لنوع معيّن. sign=-1 للحسابات الدائنة بطبيعتها
        (الخصوم وحقوق الملكية والإيرادات) لتُعرض بقيم موجبة."""
        self.ensure_one()
        currency = self.company_id.currency_id
        domain = self._base_domain(period=self.report_type == "pnl")
        domain += [("account_id.account_type", "in", account_types)]
        groups = self.env["account.move.line"].read_group(domain, ["balance:sum"], ["account_id"])
        rows = []
        total = 0.0
        for group in groups:
            balance = sign * (group["balance"] or 0.0)
            if currency.is_zero(balance):
                continue
            account = self.env["account.account"].browse(group["account_id"][0])
            rows.append({"code": account.code, "name": account.name, "balance": balance})
            total += balance
        rows.sort(key=lambda r: r["code"] or "")
        return rows, total

    def _current_result(self):
        """نتيجة الفترة حتى تاريخ التقرير: إيراد ناقص مصروف (ربح موجب)."""
        self.ensure_one()
        domain = self._base_domain(period=False)
        domain += [("account_id.account_type", "in", self._income_types() + self._expense_types())]
        groups = self.env["account.move.line"].read_group(domain, ["balance:sum"], [])
        return -(groups[0]["balance"] or 0.0) if groups else 0.0

    def _income_types(self):
        return ["income", "income_other"]

    def _expense_types(self):
        return ["expense", "expense_other", "expense_depreciation", "expense_direct_cost"]

    def _get_report_data(self):
        self.ensure_one()
        if self.report_type == "balance":
            assets, assets_t = self._section_lines([
                "asset_receivable", "asset_cash", "asset_current", "asset_non_current",
                "asset_prepayments", "asset_fixed",
            ])
            liab, liab_t = self._section_lines([
                "liability_payable", "liability_credit_card", "liability_current", "liability_non_current",
            ], sign=-1)
            equity, equity_t = self._section_lines(["equity", "equity_unaffected"], sign=-1)
            result = self._current_result()
            if not self.company_id.currency_id.is_zero(result):
                equity = equity + [{"code": "", "name": "نتيجة الفترة الجارية", "balance": result}]
                equity_t += result
            return {
                "title": "الميزانية العمومية",
                "sections": [
                    {"name": "الأصول", "lines": assets, "total": assets_t},
                    {"name": "الخصوم", "lines": liab, "total": liab_t},
                    {"name": "حقوق الملكية", "lines": equity, "total": equity_t},
                ],
                "assets_total": assets_t,
                "liab_equity_total": liab_t + equity_t,
                "difference": assets_t - (liab_t + equity_t),
            }
        income, income_t = self._section_lines(self._income_types(), sign=-1)
        expense, expense_t = self._section_lines(self._expense_types())
        return {
            "title": "قائمة الأرباح والخسائر",
            "sections": [
                {"name": "الإيرادات", "lines": income, "total": income_t},
                {"name": "المصروفات", "lines": expense, "total": expense_t},
            ],
            "net": income_t - expense_t,
        }


class HomeblendBudget(models.Model):
    _name = "homeblend.budget"
    _description = "ميزانية"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_from desc, id desc"

    name = fields.Char(string="الميزانية", required=True, tracking=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, index=True)
    currency_id = fields.Many2one(related="company_id.currency_id")
    date_from = fields.Date(string="من", required=True, default=lambda self: fields.Date.context_today(self).replace(month=1, day=1))
    date_to = fields.Date(string="إلى", required=True, default=fields.Date.context_today)
    state = fields.Selection(
        [("draft", "مسودة"), ("open", "معتمدة"), ("done", "مقفلة")],
        default="draft",
        tracking=True,
    )
    line_ids = fields.One2many("homeblend.budget.line", "budget_id", string="البنود")
    planned_total = fields.Monetary(string="المخطط", compute="_compute_totals", currency_field="currency_id")
    actual_total = fields.Monetary(string="الفعلي", compute="_compute_totals", currency_field="currency_id")
    variance_total = fields.Monetary(string="الانحراف", compute="_compute_totals", currency_field="currency_id")
    notes = fields.Text(string="ملاحظات")

    @api.depends("line_ids.planned_amount", "line_ids.actual_amount")
    def _compute_totals(self):
        for rec in self:
            rec.planned_total = sum(rec.line_ids.mapped("planned_amount"))
            rec.actual_total = sum(rec.line_ids.mapped("actual_amount"))
            rec.variance_total = rec.actual_total - rec.planned_total

    def action_open(self):
        self.write({"state": "open"})
        return True

    def action_done(self):
        self.write({"state": "done"})
        return True

    def action_draft(self):
        self.write({"state": "draft"})
        return True


class HomeblendBudgetLine(models.Model):
    _name = "homeblend.budget.line"
    _description = "بند ميزانية"

    budget_id = fields.Many2one("homeblend.budget", required=True, ondelete="cascade")
    company_id = fields.Many2one(related="budget_id.company_id", store=True)
    currency_id = fields.Many2one(related="budget_id.currency_id")
    account_id = fields.Many2one("account.account", string="الحساب", required=True)
    analytic_account_id = fields.Many2one("account.analytic.account", string="مركز التكلفة")
    planned_amount = fields.Monetary(string="المبلغ المخطط", required=True, currency_field="currency_id")
    actual_amount = fields.Monetary(string="الفعلي", compute="_compute_actual", currency_field="currency_id")
    variance_amount = fields.Monetary(string="الانحراف", compute="_compute_actual", currency_field="currency_id")

    @api.depends(
        "account_id",
        "analytic_account_id",
        "planned_amount",
        "budget_id.date_from",
        "budget_id.date_to",
        "budget_id.company_id",
    )
    def _compute_actual(self):
        AML = self.env["account.move.line"]
        for line in self:
            if not line.account_id or not line.budget_id:
                line.actual_amount = 0.0
                line.variance_amount = 0.0
                continue
            domain = [
                ("account_id", "=", line.account_id.id),
                ("parent_state", "=", "posted"),
                ("date", ">=", line.budget_id.date_from),
                ("date", "<=", line.budget_id.date_to),
                ("company_id", "=", line.budget_id.company_id.id),
                ("display_type", "not in", ["line_section", "line_note"]),
            ]
            moves = AML.search(domain)
            if line.analytic_account_id:
                key = str(line.analytic_account_id.id)
                moves = moves.filtered(lambda m: key in (m.analytic_distribution or {}))
            actual = abs(sum(moves.mapped("balance")))
            line.actual_amount = actual
            line.variance_amount = actual - line.planned_amount
