from datetime import datetime, time

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.fields import Command

try:
    from pytz import timezone, utc
except ImportError:
    timezone = utc = None


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
    extra_deduction = fields.Monetary(string="خصم يدوي إضافي")
    insurance_base = fields.Monetary(string="وعاء التأمينات", help="الحد الأقصى للأجر التأميني إن وُجد.")
    insurance_employee_rate = fields.Float(string="نسبة تأمينات العامل %", default=11.0)
    insurance_employer_rate = fields.Float(string="نسبة تأمينات صاحب العمل %", default=18.75)
    expected_hours = fields.Float(string="ساعات متوقعة", compute="_compute_time_stats", store=True)
    attendance_hours = fields.Float(string="ساعات الحضور", compute="_compute_time_stats", store=True)
    paid_leave_days = fields.Float(string="أيام إجازة مدفوعة", compute="_compute_time_stats", store=True)
    unpaid_leave_days = fields.Float(string="أيام إجازة غير مدفوعة", compute="_compute_time_stats", store=True)
    paid_leave_hours = fields.Float(string="ساعات إجازة مدفوعة", compute="_compute_time_stats", store=True)
    shortage_hours = fields.Float(string="ساعات النقص", compute="_compute_time_stats", store=True)
    time_deduction = fields.Monetary(string="خصم التأخير/الغياب", compute="_compute_time_stats", store=True)
    advance_deduction = fields.Monetary(string="خصم السلف", compute="_compute_advance_deduction", store=True)
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
    advance_ids = fields.One2many("homeblend.employee.advance", "payslip_id", string="السلف المخصومة")
    notes = fields.Text(string="ملاحظات")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) in (_("New"), "New", "جديد"):
                vals["name"] = self.env["ir.sequence"].next_by_code("homeblend.payslip") or _("New")
        return super().create(vals_list)

    @api.onchange("employee_id")
    def _onchange_employee(self):
        if self.employee_id:
            wage = self.employee_id.sudo().contract_wage or 0.0
            self.wage = wage
            self.insurance_base = min(wage, 12600.0) if wage else 0.0
            self.company_id = self.employee_id.company_id or self.env.company

    def _period_datetimes(self):
        self.ensure_one()
        start_naive = datetime.combine(self.date_from, time.min)
        end_naive = datetime.combine(self.date_to, time.max)
        tzname = (
            self.employee_id.tz
            or (self.employee_id.resource_calendar_id.tz if self.employee_id.resource_calendar_id else False)
            or "Africa/Cairo"
        )
        if timezone is None:
            return start_naive, end_naive
        tz = timezone(tzname)
        start = tz.localize(start_naive).astimezone(utc).replace(tzinfo=None)
        end = tz.localize(end_naive).astimezone(utc).replace(tzinfo=None)
        return start, end

    def _calendar(self):
        self.ensure_one()
        return self.employee_id.resource_calendar_id or self.company_id.resource_calendar_id

    @api.depends("employee_id", "date_from", "date_to", "wage", "currency_id")
    def _compute_time_stats(self):
        Attendance = self.env["hr.attendance"]
        Leave = self.env["hr.leave"]
        for slip in self:
            expected = attendance = paid_h = paid_d = unpaid_d = shortage = deduction = 0.0
            if slip.employee_id and slip.date_from and slip.date_to and slip.date_from <= slip.date_to:
                start, end = slip._period_datetimes()
                calendar = slip._calendar()
                if calendar:
                    expected = calendar.get_work_hours_count(start, end, compute_leaves=False) or 0.0
                atts = Attendance.search([
                    ("employee_id", "=", slip.employee_id.id),
                    ("check_in", ">=", start),
                    ("check_in", "<=", end),
                    ("check_out", "!=", False),
                ])
                attendance = sum(atts.mapped("worked_hours"))
                leaves = Leave.search([
                    ("employee_id", "=", slip.employee_id.id),
                    ("state", "=", "validate"),
                    ("date_from", "<=", end),
                    ("date_to", ">=", start),
                ])
                for leave in leaves:
                    overlap_start = max(leave.date_from, start)
                    overlap_end = min(leave.date_to, end)
                    hours = 0.0
                    if calendar and overlap_start < overlap_end:
                        hours = calendar.get_work_hours_count(overlap_start, overlap_end, compute_leaves=False) or 0.0
                    elif leave.number_of_hours and leave.date_from and leave.date_to:
                        total = (leave.date_to - leave.date_from).total_seconds() or 1.0
                        part = (overlap_end - overlap_start).total_seconds()
                        hours = leave.number_of_hours * max(0.0, part / total)
                    days = leave.number_of_days or 0.0
                    if leave.date_from and leave.date_to and (leave.date_from < start or leave.date_to > end):
                        span = max((leave.date_to - leave.date_from).total_seconds(), 1.0)
                        days = days * max(0.0, (overlap_end - overlap_start).total_seconds() / span)
                    if leave.holiday_status_id.unpaid:
                        unpaid_d += days
                    else:
                        paid_h += hours
                        paid_d += days
                credited = attendance + paid_h
                shortage = max(0.0, expected - credited)
                hourly = (slip.wage / expected) if expected else 0.0
                deduction = slip.currency_id.round(shortage * hourly) if slip.currency_id else shortage * hourly
            slip.expected_hours = expected
            slip.attendance_hours = attendance
            slip.paid_leave_hours = paid_h
            slip.paid_leave_days = paid_d
            slip.unpaid_leave_days = unpaid_d
            slip.shortage_hours = shortage
            slip.time_deduction = deduction

    def _open_advances(self):
        self.ensure_one()
        return self.env["homeblend.employee.advance"].search([
            ("employee_id", "=", self.employee_id.id),
            ("company_id", "=", self.company_id.id),
            ("state", "=", "confirmed"),
            ("date", "<=", self.date_to),
            ("payslip_id", "=", False),
        ])

    @api.depends("employee_id", "date_to", "company_id", "currency_id")
    def _compute_advance_deduction(self):
        for slip in self:
            amount = 0.0
            if slip.employee_id and slip.date_to:
                amount = sum(slip._open_advances().mapped("amount"))
            slip.advance_deduction = slip.currency_id.round(amount) if slip.currency_id else amount

    @api.depends(
        "wage",
        "allowances",
        "other_earnings",
        "extra_deduction",
        "insurance_base",
        "insurance_employee_rate",
        "insurance_employer_rate",
        "time_deduction",
        "advance_deduction",
        "currency_id",
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
            slip.net = slip.currency_id.round(
                gross - emp_ins - tax - slip.time_deduction - slip.advance_deduction - slip.extra_deduction
            )

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

    def action_recompute_attendance(self):
        self._compute_time_stats()
        self._compute_advance_deduction()
        self._compute_amounts()
        return True

    def action_confirm(self):
        for slip in self:
            if slip.state != "draft":
                continue
            slip.action_recompute_attendance()
            if slip.net < 0:
                raise UserError(_("صافي الراتب لا يمكن أن يكون سالباً."))
            slip._allocate_advances()
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
            slip.advance_ids.filtered(lambda a: a.state == "deducted").write({
                "state": "confirmed",
                "payslip_id": False,
            })
            slip.state = "cancelled"
        return True

    def _allocate_advances(self):
        self.ensure_one()
        advances = self._open_advances()
        if advances:
            advances.write({"state": "deducted", "payslip_id": self.id})

    def _payroll_accounts(self):
        self.ensure_one()
        company = self.company_id
        Account = self.env["account.account"].with_company(company)
        journal = company.payroll_journal_id or self.env["account.journal"].search([
            ("type", "=", "general"),
            ("company_id", "=", company.id),
        ], limit=1)
        expense = company.payroll_expense_account_id or Account.search([("account_type", "=", "expense")], limit=1)
        payable = company.payroll_payable_account_id or Account.search(
            [("account_type", "=", "liability_payable")], limit=1
        )
        insurance = company.payroll_insurance_account_id or payable
        tax = company.payroll_tax_account_id or payable
        used_fallback = not (
            company.payroll_journal_id
            and company.payroll_expense_account_id
            and company.payroll_payable_account_id
        )
        return journal, expense, payable, insurance, tax, used_fallback

    def _create_payroll_move(self):
        self.ensure_one()
        journal, expense, payable, insurance_acc, tax_acc, used_fallback = self._payroll_accounts()
        if not journal or not expense or not payable:
            self.message_post(body=_(
                "تعذر إنشاء قيد محاسبي تلقائي: أكمل شجرة الحسابات أو اضبط حسابات الرواتب على الشركة. تم اعتماد القسيمة بدون قيد."
            ))
            return
        if used_fallback:
            self.message_post(body=_(
                "تم إنشاء قيد الرواتب من أول حساب مصروف وأول حساب دائن في دليل الحسابات. اضبط حسابات الرواتب على الشركة لتثبيت القيود."
            ))
        deductions = self.time_deduction + self.advance_deduction + self.extra_deduction
        line_vals = [
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
                "account_id": insurance_acc.id,
                "debit": 0.0,
                "credit": self.insurance_employee + self.insurance_employer,
            }),
            Command.create({
                "name": _("ضريبة كسب عمل %s") % self.employee_id.name,
                "account_id": tax_acc.id,
                "debit": 0.0,
                "credit": self.tax_amount,
            }),
        ]
        if deductions:
            line_vals.append(Command.create({
                "name": _("خصم تأخير/غياب/سلفة %s") % self.employee_id.name,
                "account_id": expense.id,
                "debit": 0.0,
                "credit": deductions,
            }))
        move = self.env["account.move"].sudo().create({
            "move_type": "entry",
            "journal_id": journal.id,
            "company_id": self.company_id.id,
            "date": self.date_to,
            "ref": self.name,
            "line_ids": line_vals,
        })
        move.line_ids.filtered(lambda l: not l.debit and not l.credit).unlink()
        if abs(sum(move.line_ids.mapped("debit")) - sum(move.line_ids.mapped("credit"))) < 0.02:
            move.action_post()
        self.move_id = move
