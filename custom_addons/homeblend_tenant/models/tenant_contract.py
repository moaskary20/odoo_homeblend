from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError


class HomeblendTenantContract(models.Model):
    _name = "homeblend.tenant.contract"
    _description = "عقد مستأجر Home Blend"
    _inherit = ["mail.thread", "mail.activity.mixin", "pos.load.mixin"]
    _order = "date_start desc, id desc"

    name = fields.Char(string="المرجع", required=True, copy=False, default=lambda self: _("New"), tracking=True)
    tenant_id = fields.Many2one(
        "res.partner",
        string="المستأجر",
        required=True,
        domain="[('is_tenant', '=', True)]",
        tracking=True,
        index=True,
    )
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, index=True)
    currency_id = fields.Many2one(related="company_id.currency_id")
    date_start = fields.Date(string="بداية العقد", required=True, default=fields.Date.context_today, tracking=True)
    date_end = fields.Date(string="نهاية العقد", required=True, tracking=True)
    state = fields.Selection(
        [
            ("draft", "مسودة"),
            ("active", "ساري"),
            ("suspended", "معلق"),
            ("expired", "منتهٍ"),
            ("cancelled", "ملغى"),
            ("archived", "مؤرشف"),
        ],
        default="draft",
        tracking=True,
        copy=False,
        index=True,
    )
    commission_percent = fields.Float(string="نسبة Home Blend %", required=True, default=20.0, tracking=True)
    commission_base = fields.Selection(
        [("before_tax", "قبل الضريبة"), ("after_tax", "بعد الضريبة")],
        string="أساس الاحتساب",
        required=True,
        default="before_tax",
        tracking=True,
        help="قبل الضريبة = العمولة على المبلغ بدون ضريبة. بعد الضريبة = العمولة على إجمالي الفاتورة.",
    )
    late_fee_percent = fields.Float(string="غرامة التأخير %", default=0.0)
    payment_term_id = fields.Many2one("account.payment.term", string="شروط الدفع")
    guarantee_ids = fields.One2many(related="tenant_id.guarantee_ids", string="الضمانات")
    attachment_ids = fields.Many2many("ir.attachment", string="المرفقات")
    signed = fields.Boolean(string="موقع إلكترونياً", tracking=True)
    signed_date = fields.Datetime(string="تاريخ التوقيع")
    signed_by = fields.Many2one("res.users", string="وقّع بواسطة", copy=False)
    signature = fields.Binary(string="التوقيع", attachment=True, copy=False)
    notes = fields.Html(string="الشروط")
    sale_order_count = fields.Integer(compute="_compute_sale_order_count")
    invoice_count = fields.Integer(compute="_compute_invoice_count")
    commission_invoice_ids = fields.One2many("account.move", "homeblend_contract_id", string="فواتير العمولة")
    renewed_from_id = fields.Many2one("homeblend.tenant.contract", string="مجدَّد من", copy=False)
    expiring_soon = fields.Boolean(string="ينتهي قريباً", compute="_compute_expiring_soon", store=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code("homeblend.tenant.contract") or _("New")
        return super().create(vals_list)

    @api.constrains("date_start", "date_end")
    def _check_dates(self):
        for rec in self:
            if rec.date_end and rec.date_start and rec.date_end < rec.date_start:
                raise ValidationError(_("تاريخ النهاية يجب أن يكون بعد البداية."))

    @api.constrains("commission_percent")
    def _check_percent(self):
        for rec in self:
            if rec.commission_percent < 0 or rec.commission_percent > 100:
                raise ValidationError(_("نسبة العمولة بين 0 و 100."))

    @api.depends("date_end", "state")
    def _compute_expiring_soon(self):
        today = fields.Date.context_today(self)
        soon = today + relativedelta(days=30)
        for rec in self:
            rec.expiring_soon = bool(
                rec.state == "active" and rec.date_end and today <= rec.date_end <= soon
            )

    def _compute_sale_order_count(self):
        Sale = self.env["sale.order"]
        for rec in self:
            rec.sale_order_count = Sale.search_count([("tenant_id", "=", rec.tenant_id.id)])

    def _compute_invoice_count(self):
        Move = self.env["account.move"]
        for rec in self:
            rec.invoice_count = Move.search_count([
                ("tenant_id", "=", rec.tenant_id.id),
                ("move_type", "=", "out_invoice"),
            ])

    def action_activate(self):
        self.write({"state": "active"})
        return True

    def action_suspend(self):
        self.write({"state": "suspended"})
        return True

    def action_cancel(self):
        self.write({"state": "cancelled"})
        return True

    def action_expire(self):
        self.write({"state": "expired"})
        return True

    def action_archive_contract(self):
        self.write({"state": "archived"})
        return True

    def action_renew(self):
        for rec in self:
            if not rec.date_end:
                raise UserError(_("حدد تاريخ نهاية العقد قبل التجديد."))
            duration = rec.date_end - rec.date_start
            new_start = rec.date_end + relativedelta(days=1)
            rec.copy({
                "date_start": new_start,
                "date_end": new_start + duration,
                "state": "draft",
                "signed": False,
                "signed_date": False,
                "signed_by": False,
                "signature": False,
                "renewed_from_id": rec.id,
            })
            rec.action_expire()
        return True

    def action_sign(self):
        for rec in self:
            if not rec.signature:
                raise UserError(_("ارسم التوقيع الإلكتروني أولاً قبل اعتماده."))
        self.write({
            "signed": True,
            "signed_date": fields.Datetime.now(),
            "signed_by": self.env.user.id,
        })
        return True

    def action_view_invoices(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("فواتير المستأجر"),
            "res_model": "account.move",
            "view_mode": "list,form",
            "domain": [
                ("tenant_id", "=", self.tenant_id.id),
                ("move_type", "in", ["out_invoice", "out_refund"]),
            ],
        }

    def action_view_sales(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("مبيعات المستأجر"),
            "res_model": "sale.order",
            "view_mode": "list,form",
            "domain": [("tenant_id", "=", self.tenant_id.id)],
        }

    @api.model
    def _load_pos_data_domain(self, data, config):
        today = fields.Date.context_today(self)
        return [
            ("state", "=", "active"),
            ("company_id", "=", config.company_id.id),
            ("date_start", "<=", today),
            ("date_end", ">=", today),
        ]

    @api.model
    def _load_pos_data_fields(self, config):
        return [
            "name",
            "tenant_id",
            "company_id",
            "commission_percent",
            "commission_base",
            "payment_term_id",
            "state",
            "date_start",
            "date_end",
        ]

    @api.model
    def get_active_for_tenant(self, tenant, company=None):
        company = company or self.env.company
        return self.search([
            ("tenant_id", "=", tenant.id),
            ("company_id", "=", company.id),
            ("state", "=", "active"),
            ("date_start", "<=", fields.Date.context_today(self)),
            ("date_end", ">=", fields.Date.context_today(self)),
        ], limit=1, order="date_start desc")

    @api.model
    def _cron_expire_and_notify(self):
        today = fields.Date.context_today(self)
        soon = today + relativedelta(days=30)
        self.search([("state", "=", "active"), ("date_end", "<", today)]).action_expire()
        expiring = self.search([("state", "=", "active"), ("date_end", ">=", today), ("date_end", "<=", soon)])
        for contract in expiring:
            if self.env["mail.activity"].search([
                ("res_model", "=", "homeblend.tenant.contract"),
                ("res_id", "=", contract.id),
                ("summary", "ilike", "ينتهي قريباً"),
            ], limit=1):
                continue
            contract.activity_schedule(
                "mail.mail_activity_data_todo",
                summary=_("العقد %s ينتهي قريباً") % contract.name,
                date_deadline=contract.date_end,
            )
