from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class ArtcasaStockReservation(models.Model):
    _name = "artcasa.stock.reservation"
    _description = "حجز مخزون مندوب Art Casa"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_end, id desc"

    name = fields.Char(string="المرجع", required=True, copy=False, default=lambda self: _("New"), tracking=True)
    user_id = fields.Many2one(
        "res.users",
        string="المندوب",
        required=True,
        default=lambda self: self.env.user,
        tracking=True,
    )
    partner_id = fields.Many2one("res.partner", string="العميل", required=True, tracking=True)
    product_id = fields.Many2one(
        "product.product",
        string="المنتج",
        required=True,
        tracking=True,
        check_company=True,
    )
    product_uom_id = fields.Many2one(related="product_id.uom_id")
    quantity = fields.Float(string="الكمية", required=True, default=1.0, tracking=True)
    warehouse_id = fields.Many2one(
        "stock.warehouse",
        string="المخزن",
        required=True,
        check_company=True,
        default=lambda self: self.env["stock.warehouse"].search(
            [("company_id", "=", self.env.company.id)], limit=1
        ),
        tracking=True,
    )
    company_id = fields.Many2one(related="warehouse_id.company_id", store=True)
    date_start = fields.Datetime(
        string="بداية الحجز",
        required=True,
        default=fields.Datetime.now,
        tracking=True,
    )
    date_end = fields.Datetime(
        string="نهاية الحجز",
        required=True,
        default=lambda self: fields.Datetime.now() + timedelta(days=7),
        tracking=True,
    )
    location_dest_id = fields.Many2one("stock.location", string="موقع الحجز")
    picking_id = fields.Many2one("stock.picking", string="تحويل الحجز", copy=False)
    sale_order_id = fields.Many2one("sale.order", string="أمر البيع", copy=False)
    state = fields.Selection(
        [
            ("draft", "مسودة"),
            ("reserved", "محجوز"),
            ("consumed", "مستهلك"),
            ("released", "محرّر"),
        ],
        default="draft",
        tracking=True,
        copy=False,
        required=True,
    )
    is_active = fields.Boolean(string="ساري الآن", compute="_compute_availability", search="_search_is_active")
    qty_on_hand = fields.Float(string="المخزون الفعلي", compute="_compute_availability")
    qty_reserved_others = fields.Float(string="محجوز لآخرين", compute="_compute_availability")
    qty_free = fields.Float(string="المتاح للبيع", compute="_compute_availability")
    notes = fields.Text(string="ملاحظات")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code("artcasa.stock.reservation") or _("New")
        records = super().create(vals_list)
        records.filtered(lambda r: r.state == "reserved")._check_capacity()
        return records

    def write(self, vals):
        res = super().write(vals)
        if {"quantity", "product_id", "warehouse_id", "date_start", "date_end", "state"} & set(vals):
            self.filtered(lambda r: r.state == "reserved")._check_capacity()
        return res

    @api.constrains("date_start", "date_end", "quantity")
    def _check_dates_qty(self):
        for rec in self:
            if rec.quantity <= 0:
                raise ValidationError(_("حدد كمية أكبر من صفر."))
            if rec.date_start and rec.date_end and rec.date_end <= rec.date_start:
                raise ValidationError(_("تاريخ نهاية الحجز يجب أن يكون بعد تاريخ البداية."))

    @api.depends("product_id", "warehouse_id", "quantity", "date_start", "date_end", "state")
    def _compute_availability(self):
        now = fields.Datetime.now()
        for rec in self:
            rec.is_active = bool(
                rec.state == "reserved" and rec.date_start and rec.date_end and rec.date_start <= now <= rec.date_end
            )
            on_hand = rec._warehouse_on_hand()
            others = rec._overlapping_qty(exclude_self=True)
            rec.qty_on_hand = on_hand
            rec.qty_reserved_others = others
            rec.qty_free = on_hand - others - (rec.quantity if rec.state == "reserved" else 0.0)

    def _search_is_active(self, operator, value):
        now = fields.Datetime.now()
        active_domain = [
            ("state", "=", "reserved"),
            ("date_start", "<=", now),
            ("date_end", ">=", now),
        ]
        want_active = (operator == "=" and value) or (operator == "!=" and not value)
        if want_active:
            return active_domain
        return ["!"] + active_domain

    def _warehouse_on_hand(self):
        self.ensure_one()
        if not self.product_id or not self.warehouse_id:
            return 0.0
        return self.product_id.with_context(
            warehouse_id=self.warehouse_id.id,
            skip_artcasa_reservation=True,
        ).qty_available

    def _overlapping_domain(self):
        self.ensure_one()
        return [
            ("product_id", "=", self.product_id.id),
            ("warehouse_id", "=", self.warehouse_id.id),
            ("state", "=", "reserved"),
            ("date_start", "<=", self.date_end),
            ("date_end", ">=", self.date_start),
        ]

    def _overlapping_qty(self, exclude_self=True):
        self.ensure_one()
        if not self.product_id or not self.warehouse_id or not self.date_start or not self.date_end:
            return 0.0
        domain = self._overlapping_domain()
        if exclude_self and self.id:
            domain.append(("id", "!=", self.id))
        return sum(self.search(domain).mapped("quantity"))

    def _check_capacity(self):
        for rec in self:
            rec._lock_overlapping()
            on_hand = rec._warehouse_on_hand()
            taken = rec._overlapping_qty(exclude_self=True)
            if taken + rec.quantity > on_hand + 1e-6:
                raise UserError(_(
                    "لا يمكن حجز %(qty)s من %(product)s في %(wh)s. "
                    "المخزون الفعلي %(on_hand)s والمحجوز في نفس الفترة %(taken)s. "
                    "لا يُسمح لأكثر من مندوب بحجز نفس الكمية في نفس الوقت."
                ) % {
                    "qty": rec.quantity,
                    "product": rec.product_id.display_name,
                    "wh": rec.warehouse_id.display_name,
                    "on_hand": on_hand,
                    "taken": taken,
                })

    def _lock_overlapping(self):
        self.ensure_one()
        if not self.product_id or not self.warehouse_id:
            return
        self.env.cr.execute(
            """
            SELECT id FROM artcasa_stock_reservation
            WHERE product_id = %s AND warehouse_id = %s AND state = 'reserved'
              AND date_start <= %s AND date_end >= %s
            FOR UPDATE
            """,
            [self.product_id.id, self.warehouse_id.id, self.date_end, self.date_start],
        )

    def action_reserve(self):
        for rec in self:
            if rec.state != "draft":
                continue
            rec._check_capacity()
            rec.write({"state": "reserved"})
            rec.message_post(body=_(
                "تم الحجز افتراضياً دون صرف من المخزن. الكمية غير متاحة للبيع حتى %s."
            ) % rec.date_end)
        return True

    def action_release(self):
        for rec in self:
            if rec.state != "reserved":
                continue
            rec.write({"state": "released"})
            rec.message_post(body=_("تم تحرير الكمية وإعادتها للمخزون المتاح."))
        return True

    def action_consume(self):
        self.filtered(lambda r: r.state == "reserved").write({"state": "consumed"})
        return True

    @api.model
    def _cron_release_expired(self):
        expired = self.search([
            ("state", "=", "reserved"),
            ("date_end", "<", fields.Datetime.now()),
        ])
        expired.action_release()
        return True

    def action_release_expired(self):
        self._cron_release_expired()
        return True
