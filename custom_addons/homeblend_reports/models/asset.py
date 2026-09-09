from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.fields import Command


class HomeblendAsset(models.Model):
    _name = "homeblend.asset"
    _description = "أصل ثابت"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_start desc, id desc"

    name = fields.Char(string="الأصل", required=True, tracking=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, index=True)
    currency_id = fields.Many2one(related="company_id.currency_id")
    partner_id = fields.Many2one("res.partner", string="المورّد")
    date_start = fields.Date(string="تاريخ الشراء", required=True, default=fields.Date.context_today)
    purchase_value = fields.Monetary(string="تكلفة الشراء", required=True)
    salvage_value = fields.Monetary(string="قيمة الخردة")
    method_years = fields.Integer(string="سنوات الإهلاك", default=5, required=True)
    annual_depreciation = fields.Monetary(string="الإهلاك السنوي", compute="_compute_annual_depreciation", store=True)
    accumulated = fields.Monetary(string="مجمع الإهلاك", compute="_compute_book_value")
    residual = fields.Monetary(string="القيمة الدفترية", compute="_compute_book_value")
    state = fields.Selection(
        [("draft", "مسودة"), ("running", "قيد الإهلاك"), ("closed", "مقفول")],
        default="draft",
        tracking=True,
    )
    notes = fields.Text(string="ملاحظات")
    last_depreciation_date = fields.Date(string="آخر قيد إهلاك", copy=False)
    depreciation_move_ids = fields.Many2many(
        "account.move",
        "homeblend_asset_move_rel",
        "asset_id",
        "move_id",
        string="قيود الإهلاك",
        copy=False,
    )

    @api.depends("purchase_value", "salvage_value", "method_years")
    def _compute_annual_depreciation(self):
        for rec in self:
            years = rec.method_years or 1
            depreciable = max(0.0, rec.purchase_value - rec.salvage_value)
            rec.annual_depreciation = rec.currency_id.round(depreciable / years) if depreciable else 0.0

    @api.depends("annual_depreciation", "date_start", "method_years", "purchase_value")
    def _compute_book_value(self):
        today = fields.Date.context_today(self)
        for rec in self:
            years = rec.method_years or 1
            annual = rec.annual_depreciation or 0.0
            elapsed = 0
            if rec.date_start:
                elapsed = max(0, (today.year - rec.date_start.year))
                if today.month < rec.date_start.month or (today.month == rec.date_start.month and today.day < rec.date_start.day):
                    elapsed = max(0, elapsed - 1)
            elapsed = min(elapsed, years)
            rec.accumulated = rec.currency_id.round(annual * elapsed)
            rec.residual = rec.currency_id.round(rec.purchase_value - rec.accumulated)

    def action_start(self):
        self.write({"state": "running"})
        return True

    def action_close(self):
        self.write({"state": "closed"})
        return True

    def _get_depreciation_accounts(self):
        self.ensure_one()
        Account = self.env["account.account"].with_company(self.company_id)
        expense = Account.search([
            ("account_type", "=", "expense_depreciation"),
            ("company_ids", "in", self.company_id.id),
        ], limit=1)
        if not expense:
            expense = Account.search([
                ("account_type", "=", "expense"),
                ("company_ids", "in", self.company_id.id),
            ], limit=1)
        accum = Account.search([
            ("account_type", "=", "asset_non_current"),
            ("company_ids", "in", self.company_id.id),
        ], limit=1)
        if not accum:
            accum = Account.search([
                ("account_type", "=", "asset_fixed"),
                ("company_ids", "in", self.company_id.id),
            ], limit=1)
        return expense, accum

    def action_post_depreciation(self):
        today = fields.Date.context_today(self)
        for rec in self:
            if rec.state != "running":
                raise UserError(_("ابدأ الإهلاك قبل ترحيل القيد."))
            if rec.last_depreciation_date and rec.last_depreciation_date.month == today.month and rec.last_depreciation_date.year == today.year:
                continue
            monthly = rec.currency_id.round((rec.annual_depreciation or 0.0) / 12.0)
            if monthly <= 0:
                continue
            expense, accum = rec._get_depreciation_accounts()
            journal = rec.env["account.journal"].search([
                ("type", "=", "general"),
                ("company_id", "=", rec.company_id.id),
            ], limit=1)
            if not expense or not accum or not journal:
                raise UserError(_("تعذر إيجاد حسابات أو يومية للإهلاك في %s.") % rec.company_id.name)
            move = rec.env["account.move"].create({
                "move_type": "entry",
                "journal_id": journal.id,
                "company_id": rec.company_id.id,
                "date": today,
                "ref": _("إهلاك %s") % rec.name,
                "line_ids": [
                    Command.create({
                        "name": _("مصروف إهلاك %s") % rec.name,
                        "account_id": expense.id,
                        "debit": monthly,
                        "credit": 0.0,
                    }),
                    Command.create({
                        "name": _("مجمع إهلاك %s") % rec.name,
                        "account_id": accum.id,
                        "debit": 0.0,
                        "credit": monthly,
                    }),
                ],
            })
            move.action_post()
            rec.write({
                "last_depreciation_date": today,
                "depreciation_move_ids": [Command.link(move.id)],
            })
        return True

    @api.model
    def _cron_post_depreciation(self):
        self.search([("state", "=", "running")]).action_post_depreciation()
        return True
