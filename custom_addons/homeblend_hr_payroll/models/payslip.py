from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.fields import Command


class HomeblendPayslip(models.Model):
    _name = "homeblend.payslip"
    _description = "قسيمة راتب مصرية"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_to desc, id desc"

    name = fields.Char(string="المرجع", required=True, copy=False, default=lambda self: _("New"))
    employee_id = fields.Many2one("hr.employee", string="الموظف", required=True, tracking=True)
    department_id = fields.Many2one(related="employee_id.department_id", store=True)
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    currency_id = fields.Many2one(related="company_id.currency_id")
    date_from = fields.Date(string="من", required=True, default=lambda self: fields.Date.today().replace(day=1))
    date_to = fields.Date(string="إلى", required=True, default=fields.Date.context_today)
    wage = fields.Monetary(string="الأجر الأساسي", required=True)
    allowances = fields.Monetary(string="البدلات")
    other_earnings = fields.Monetary(string="مستحقات أخرى")
    insurance_base = fields.Monetary(string="وعاء التأمينات", help="الحد الأقصى للأجر التأميني إن وُجد.")
    insurance_employee_rate = fields.Float(string="نسبة تأمينات العامل %", default=11.0)
    insurance_employer_rate = fields.Float(string="نسبة تأمينات صاحب العمل %", default=18.75)
    insurance_employee = fields.Monetary(string="تأمينات العامل", compute="_compute_amounts", store=True)
    insurance_employer = fields.Monetary(string="تأمينات صاحب العمل", compute="_compute_amounts", store=True)
    tax_amount = fields.Monetary(string="ضريبة كسب العمل", compute="_compute_amounts", store=True)
    gross = fields.Monetary(string="الإجمالي", compute="_compute_amounts", store=True)
    net = fields.Monetary(string="الصافي", compute="_compute_amounts", store=True)
    state = fields.Selection(
        [("draft", "مسودة"), ("confirmed", "معتمدة"), ("paid", "مدفوعة"), ("cancelled", "ملغاة")],
        default="draft",
        tracking=True,
        copy=False,
    )
    move_id = fields.Many2one("account.move", string="قيد اليومية", copy=False)
    notes = fields.Text(string="ملاحظات")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code("homeblend.payslip") or _("New")
        return super().create(vals_list)

    @api.onchange("employee_id")
    def _onchange_employee(self):
        if self.employee_id:
            wage = self.employee_id.sudo().contract_wage or 0.0
            self.wage = wage
            self.insurance_base = min(wage, 12600.0) if wage else 0.0
            self.company_id = self.employee_id.company_id or self.env.company

    @api.depends(
        "wage",
        "allowances",
        "other_earnings",
        "insurance_base",
        "insurance_employee_rate",
        "insurance_employer_rate",
    )
    def _compute_amounts(self):
        for slip in self:
            gross = slip.wage + slip.allowances + slip.other_earnings
            base = slip.insurance_base or slip.wage
            emp_ins = slip.currency_id.round(base * (slip.insurance_employee_rate / 100.0)) if base else 0.0
            er_ins = slip.currency_id.round(base * (slip.insurance_employer_rate / 100.0)) if base else 0.0
            taxable_monthly = max(0.0, gross - emp_ins)
            tax = slip._egyptian_monthly_tax(taxable_monthly)
            slip.gross = gross
            slip.insurance_employee = emp_ins
            slip.insurance_employer = er_ins
            slip.tax_amount = tax
            slip.net = slip.currency_id.round(gross - emp_ins - tax)

    def _egyptian_monthly_tax(self, monthly_taxable):
        """Approximate Egyptian salary tax on an annualized basis (2024/2025 brackets)."""
        annual = monthly_taxable * 12.0
        exemption = 20000.0
        taxable = max(0.0, annual - exemption)
        brackets = [
            (40000, 0.00),
            (15000, 0.10),
            (15000, 0.15),
            (130000, 0.20),
            (200000, 0.225),
            (800000, 0.25),
            (False, 0.275),
        ]
        remaining = taxable
        tax = 0.0
        for width, rate in brackets:
            if remaining <= 0:
                break
            chunk = remaining if width is False else min(remaining, width)
            tax += chunk * rate
            remaining -= chunk
        return self.currency_id.round(tax / 12.0)

    def action_confirm(self):
        for slip in self:
            if slip.state != "draft":
                continue
            if slip.net < 0:
                raise UserError(_("صافي الراتب لا يمكن أن يكون سالباً."))
            slip._create_payroll_move()
            slip.state = "confirmed"
        return True

    def action_mark_paid(self):
        self.filtered(lambda s: s.state == "confirmed").write({"state": "paid"})
        return True

    def action_cancel(self):
        for slip in self:
            if slip.move_id and slip.move_id.state == "posted":
                slip.move_id.button_draft()
                slip.move_id.button_cancel()
            slip.state = "cancelled"
        return True

    def _create_payroll_move(self):
        self.ensure_one()
        journal = self.env["account.journal"].search([
            ("type", "=", "general"),
            ("company_id", "=", self.company_id.id),
        ], limit=1)
        Account = self.env["account.account"].with_company(self.company_id)
        expense = Account.search([
            ("account_type", "=", "expense"),
        ], limit=1)
        payable = Account.search([
            ("account_type", "=", "liability_payable"),
        ], limit=1)
        if not journal or not expense or not payable:
            self.message_post(body=_("تعذر إنشاء قيد محاسبي تلقائي: أكمل شجرة الحسابات ثم أعد الاعتماد."))
            return
        move = self.env["account.move"].sudo().create({
            "move_type": "entry",
            "journal_id": journal.id,
            "company_id": self.company_id.id,
            "date": self.date_to,
            "ref": self.name,
            "line_ids": [
                Command.create({
                    "name": _("راتب %s") % self.employee_id.name,
                    "account_id": expense.id,
                    "debit": self.gross + self.insurance_employer,
                    "credit": 0.0,
                }),
                Command.create({
                    "name": _("صافي راتب %s") % self.employee_id.name,
                    "account_id": payable.id,
                    "debit": 0.0,
                    "credit": self.net,
                }),
                Command.create({
                    "name": _("تأمينات %s") % self.employee_id.name,
                    "account_id": payable.id,
                    "debit": 0.0,
                    "credit": self.insurance_employee + self.insurance_employer,
                }),
                Command.create({
                    "name": _("ضريبة كسب عمل %s") % self.employee_id.name,
                    "account_id": payable.id,
                    "debit": 0.0,
                    "credit": self.tax_amount,
                }),
            ],
        })
        # Drop zero lines
        move.line_ids.filtered(lambda l: not l.debit and not l.credit).unlink()
        if abs(sum(move.line_ids.mapped("debit")) - sum(move.line_ids.mapped("credit"))) < 0.02:
            move.action_post()
        self.move_id = move
