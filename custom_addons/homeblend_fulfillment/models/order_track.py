from datetime import timedelta

from odoo import api, fields, models, _


TRACK_STATES = [
    ("draft", "Draft"),
    ("confirmed", "Confirmed"),
    ("processing", "Processing"),
    ("ready", "Ready"),
    ("delivered", "Delivered"),
    ("completed", "Completed"),
    ("delayed", "Delayed"),
    ("cancelled", "Cancelled"),
    ("returned", "Returned"),
]


class HomeblendOrderTrack(models.Model):
    _name = "homeblend.order.track"
    _description = "تتبع عملية بيع"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(string="رقم العملية", required=True, copy=False, default=lambda self: _("New"))
    sale_order_id = fields.Many2one("sale.order", required=True, ondelete="cascade", index=True, tracking=True)
    partner_id = fields.Many2one(related="sale_order_id.partner_id", store=True)
    tenant_id = fields.Many2one("res.partner", related="sale_order_id.tenant_id", store=True)
    invoice_ids = fields.Many2many("account.move", related="sale_order_id.invoice_ids")
    date_order = fields.Datetime(related="sale_order_id.date_order", store=True)
    commitment_date = fields.Datetime(related="sale_order_id.commitment_date", store=True)
    user_id = fields.Many2one(related="sale_order_id.user_id", store=True)
    company_id = fields.Many2one(related="sale_order_id.company_id", store=True)
    amount_total = fields.Monetary(related="sale_order_id.amount_total", store=True)
    currency_id = fields.Many2one(related="sale_order_id.currency_id", store=True)
    progress = fields.Float(string="نسبة الإنجاز", compute="_compute_progress", store=True)
    state = fields.Selection(TRACK_STATES, default="draft", tracking=True, index=True, copy=False)
    delivery_state = fields.Char(compute="_compute_delivery_state")
    notes = fields.Text(string="ملاحظات")
    attachment_ids = fields.Many2many("ir.attachment", string="المرفقات")
    payment_state = fields.Selection(
        [
            ("not_paid", "غير مدفوع"),
            ("partial", "جزئي"),
            ("in_payment", "قيد التحصيل"),
            ("paid", "مدفوع"),
            ("reversed", "معكوس"),
            ("invoicing_legacy", "قديم"),
        ],
        string="حالة الدفع",
        compute="_compute_payment_state",
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code("homeblend.order.track") or _("New")
        return super().create(vals_list)

    @api.depends("state")
    def _compute_progress(self):
        mapping = {
            "draft": 5,
            "confirmed": 15,
            "processing": 40,
            "ready": 70,
            "delivered": 90,
            "completed": 100,
            "delayed": 50,
            "cancelled": 0,
            "returned": 20,
        }
        for rec in self:
            rec.progress = mapping.get(rec.state, 0)

    def _compute_delivery_state(self):
        for rec in self:
            rec.delivery_state = rec.state

    def _compute_payment_state(self):
        for rec in self:
            invoices = rec.sale_order_id.invoice_ids.filtered(
                lambda m: m.move_type == "out_invoice" and m.state == "posted"
            )
            if not invoices:
                rec.payment_state = False
            elif all(inv.payment_state == "paid" for inv in invoices):
                rec.payment_state = "paid"
            elif any(inv.payment_state in ("partial", "in_payment") for inv in invoices):
                rec.payment_state = "partial"
            else:
                rec.payment_state = invoices[:1].payment_state or "not_paid"

    def action_set_state(self):
        state = self.env.context.get("next_state")
        if state:
            self.write({"state": state})
        return True

    def action_confirmed(self):
        self.write({"state": "confirmed"})
        return True

    def action_processing(self):
        self.write({"state": "processing"})
        return True

    def action_ready(self):
        self.write({"state": "ready"})
        return True

    def action_delivered(self):
        self.write({"state": "delivered"})
        return True

    def action_completed(self):
        self.write({"state": "completed"})
        return True

    def action_delayed(self):
        self.write({"state": "delayed"})
        return True

    def action_cancelled(self):
        self.write({"state": "cancelled"})
        return True

    def action_returned(self):
        self.write({"state": "returned"})
        return True

    @api.model
    def _cron_mark_delayed(self):
        today = fields.Datetime.now()
        late = self.search([
            ("state", "in", ["confirmed", "processing", "ready"]),
            ("commitment_date", "!=", False),
            ("commitment_date", "<", today),
        ])
        late.action_delayed()
        Activity = self.env["mail.activity"]
        for rec in late:
            if not Activity.search([
                ("res_model", "=", "homeblend.order.track"),
                ("res_id", "=", rec.id),
                ("summary", "ilike", "طلب متأخر"),
            ], limit=1):
                rec.activity_schedule(
                    "mail.mail_activity_data_todo",
                    summary=_("طلب متأخر %s") % rec.name,
                )
        approaching = self.search([
            ("state", "in", ["confirmed", "processing", "ready"]),
            ("commitment_date", "!=", False),
            ("commitment_date", ">=", fields.Datetime.now()),
            ("commitment_date", "<=", fields.Datetime.now() + timedelta(days=2)),
        ])
        for rec in approaching:
            if not Activity.search([
                ("res_model", "=", "homeblend.order.track"),
                ("res_id", "=", rec.id),
                ("summary", "ilike", "اقتراب موعد التسليم"),
            ], limit=1):
                rec.activity_schedule(
                    "mail.mail_activity_data_todo",
                    summary=_("اقتراب موعد التسليم %s") % rec.name,
                    date_deadline=fields.Date.context_today(self),
                )
        overdue = self.env["account.move"].search([
            ("move_type", "=", "out_invoice"),
            ("payment_state", "in", ["not_paid", "partial"]),
            ("invoice_date_due", "<", fields.Date.context_today(self)),
            ("state", "=", "posted"),
        ], limit=80)
        for inv in overdue:
            if Activity.search([
                ("res_model", "=", "account.move"),
                ("res_id", "=", inv.id),
                ("summary", "ilike", "تأخر سداد"),
            ], limit=1):
                continue
            inv.activity_schedule(
                "mail.mail_activity_data_todo",
                summary=_("تأخر سداد الفاتورة %s") % inv.name,
                date_deadline=fields.Date.context_today(self),
            )
        self._cron_supplier_delay(Activity)
        self._cron_coupon_loyalty_expiry(Activity)
        self._cron_credit_limit(Activity)
        self._cron_low_stock(Activity)

    def _cron_supplier_delay(self, Activity):
        if "purchase.order" not in self.env:
            return
        late_pos = self.env["purchase.order"].search([
            ("state", "=", "purchase"),
            ("date_planned", "!=", False),
            ("date_planned", "<", fields.Datetime.now()),
        ], limit=40)
        for po in late_pos:
            pending = po.picking_ids.filtered(lambda p: p.state not in ("done", "cancel"))
            if po.picking_ids and not pending:
                continue
            if Activity.search([
                ("res_model", "=", "purchase.order"),
                ("res_id", "=", po.id),
                ("summary", "ilike", "تأخر المورد"),
            ], limit=1):
                continue
            po.activity_schedule(
                "mail.mail_activity_data_todo",
                summary=_("تأخر المورد في أمر الشراء %s") % po.name,
                date_deadline=fields.Date.context_today(self),
            )

    def _cron_coupon_loyalty_expiry(self, Activity):
        if "loyalty.card" not in self.env:
            return
        today = fields.Date.context_today(self)
        soon = today + timedelta(days=7)
        cards = self.env["loyalty.card"].search([
            ("expiration_date", "!=", False),
            ("expiration_date", ">=", today),
            ("expiration_date", "<=", soon),
            ("points", ">", 0),
        ], limit=40)
        for card in cards:
            if Activity.search([
                ("res_model", "=", "loyalty.card"),
                ("res_id", "=", card.id),
                ("summary", "ilike", "صلاحية الكوبون"),
            ], limit=1):
                continue
            card.activity_schedule(
                "mail.mail_activity_data_todo",
                summary=_("انتهاء صلاحية الكوبون %s") % card.code,
                date_deadline=card.expiration_date,
            )
        programs = self.env["loyalty.program"].search([
            ("date_to", "!=", False),
            ("date_to", ">=", today),
            ("date_to", "<=", today + timedelta(days=30)),
        ], limit=20)
        for program in programs:
            if Activity.search([
                ("res_model", "=", "loyalty.program"),
                ("res_id", "=", program.id),
                ("summary", "ilike", "نقاط الولاء"),
            ], limit=1):
                continue
            program.activity_schedule(
                "mail.mail_activity_data_todo",
                summary=_("انتهاء نقاط الولاء: %s") % program.name,
                date_deadline=program.date_to,
            )

    def _cron_credit_limit(self, Activity):
        partners = self.env["res.partner"].sudo().search([
            ("credit_limit", ">", 0),
        ], limit=80)
        for partner in partners:
            if partner.credit <= partner.credit_limit:
                continue
            if Activity.search([
                ("res_model", "=", "res.partner"),
                ("res_id", "=", partner.id),
                ("summary", "ilike", "الحد الائتماني"),
            ], limit=1):
                continue
            partner.activity_schedule(
                "mail.mail_activity_data_todo",
                summary=_("تجاوز الحد الائتماني: %s") % partner.display_name,
                date_deadline=fields.Date.context_today(self),
            )

    def _cron_low_stock(self, Activity):
        if "stock.warehouse.orderpoint" not in self.env:
            return
        for op in self.env["stock.warehouse.orderpoint"].search([], limit=80):
            if op.qty_on_hand > op.product_min_qty:
                continue
            summary = _("انخفاض المخزون: %s في %s") % (op.product_id.display_name, op.warehouse_id.display_name)
            if Activity.search([
                ("res_model", "=", "product.product"),
                ("res_id", "=", op.product_id.id),
                ("summary", "ilike", "انخفاض المخزون"),
            ], limit=1):
                continue
            op.product_id.activity_schedule(
                "mail.mail_activity_data_todo",
                summary=summary,
                date_deadline=fields.Date.context_today(self),
            )
