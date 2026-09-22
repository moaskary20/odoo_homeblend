from odoo import api, fields, models, _


class HomeblendEmployeeAdvance(models.Model):
    _name = "homeblend.employee.advance"
    _description = "سلفة موظف"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date desc, id desc"

    name = fields.Char(string="المرجع", required=True, copy=False, default=lambda self: _("New"))
    employee_id = fields.Many2one("hr.employee", string="الموظف", required=True, tracking=True, index=True)
    date = fields.Date(string="التاريخ", required=True, default=fields.Date.context_today, tracking=True)
    amount = fields.Monetary(string="المبلغ", required=True, tracking=True)
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    currency_id = fields.Many2one(related="company_id.currency_id")
    state = fields.Selection(
        [
            ("draft", "مسودة"),
            ("confirmed", "مؤكدة"),
            ("deducted", "مخصومة"),
            ("cancelled", "ملغاة"),
        ],
        default="draft",
        required=True,
        tracking=True,
        copy=False,
    )
    payslip_id = fields.Many2one("homeblend.payslip", string="قسيمة الراتب", copy=False, readonly=True)
    notes = fields.Text(string="ملاحظات")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) in (_("New"), "New", "جديد"):
                vals["name"] = self.env["ir.sequence"].next_by_code("homeblend.employee.advance") or _("New")
        return super().create(vals_list)

    @api.onchange("employee_id")
    def _onchange_employee(self):
        if self.employee_id:
            self.company_id = self.employee_id.company_id or self.env.company

    def action_confirm(self):
        self.filtered(lambda r: r.state == "draft").write({"state": "confirmed"})
        return True

    def action_cancel(self):
        self.filtered(lambda r: r.state in ("draft", "confirmed")).write({"state": "cancelled"})
        return True
