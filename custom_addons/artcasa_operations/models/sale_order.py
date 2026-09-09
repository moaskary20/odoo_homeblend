from odoo import api, fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    extra_cost_total = fields.Monetary(
        string="تكاليف إضافية",
        compute="_compute_artcasa_margin",
        store=True,
        currency_field="currency_id",
    )
    margin_after_extra = fields.Monetary(
        string="الربح بعد التكاليف الإضافية",
        compute="_compute_artcasa_margin",
        store=True,
        currency_field="currency_id",
    )
    margin_percent_after_extra = fields.Float(
        string="نسبة الربح %",
        compute="_compute_artcasa_margin",
        store=True,
    )
    actual_cost_total = fields.Monetary(
        string="التكلفة الفعلية",
        compute="_compute_artcasa_margin",
        store=True,
        currency_field="currency_id",
    )
    net_profit = fields.Monetary(
        string="صافي الربح",
        compute="_compute_artcasa_margin",
        store=True,
        currency_field="currency_id",
    )

    @api.depends(
        "order_line.extra_cost_total",
        "order_line.margin_after_extra",
        "order_line.display_type",
        "order_line.price_subtotal",
        "order_line.purchase_price",
        "order_line.product_uom_qty",
        "amount_total",
        "amount_untaxed",
        "company_id.artcasa_margin_include_tax",
    )
    def _compute_artcasa_margin(self):
        for order in self:
            lines = order.order_line.filtered(lambda l: not l.display_type)
            extra = sum(lines.mapped("extra_cost_total"))
            cost = sum(line.purchase_price * line.product_uom_qty for line in lines)
            order.extra_cost_total = extra
            order.actual_cost_total = cost + extra
            order.margin_after_extra = sum(lines.mapped("margin_after_extra"))
            revenue = order.amount_total if order.company_id.artcasa_margin_include_tax else order.amount_untaxed
            order.net_profit = revenue - order.actual_cost_total
            base = revenue or sum(lines.mapped("price_subtotal"))
            order.margin_percent_after_extra = (order.net_profit / base * 100.0) if base else 0.0

    def _prepare_invoice(self):
        vals = super()._prepare_invoice()
        if self.project_id:
            vals["artcasa_project_id"] = self.project_id.id
            if self.project_id.payment_term_id:
                vals["invoice_payment_term_id"] = self.project_id.payment_term_id.id
        return vals

    def _create_invoices(self, grouped=False, final=False, date=None):
        invoices = super()._create_invoices(grouped=grouped, final=final, date=date)
        if self.env.context.get("artcasa_skip_split"):
            return invoices
        extra = self.env["account.move"]
        for move in invoices:
            extra |= move._artcasa_split_invoice()
        return invoices | extra

    def action_confirm(self):
        self._artcasa_consume_reservations()
        return super().action_confirm()

    def _artcasa_consume_reservations(self):
        Reservation = self.env["artcasa.stock.reservation"]
        now = fields.Datetime.now()
        for order in self:
            for line in order.order_line.filtered(
                lambda l: l.display_type not in ("line_section", "line_subsection", "line_note") and l.product_id
            ):
                remaining = line.product_uom_qty
                reserved = Reservation.search([
                    ("user_id", "=", order.user_id.id),
                    ("product_id", "=", line.product_id.id),
                    ("warehouse_id", "=", order.warehouse_id.id),
                    ("state", "=", "reserved"),
                    ("date_start", "<=", now),
                    ("date_end", ">=", now),
                    ("company_id", "=", order.company_id.id),
                ], order="date_end, id")
                for rec in reserved:
                    if remaining <= 0:
                        break
                    rec.sale_order_id = order.id
                    if rec.quantity <= remaining + 1e-6:
                        remaining -= rec.quantity
                        rec.action_consume()
                    else:
                        rec.quantity = rec.quantity - remaining
                        remaining = 0.0


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    extra_cost_unit = fields.Monetary(
        string="تكلفة إضافية للوحدة",
        compute="_compute_artcasa_line_margin",
        store=True,
        currency_field="currency_id",
    )
    extra_cost_total = fields.Monetary(
        string="تكاليف إضافية",
        compute="_compute_artcasa_line_margin",
        store=True,
        currency_field="currency_id",
    )
    margin_after_extra = fields.Monetary(
        string="ربح بعد الإضافي",
        compute="_compute_artcasa_line_margin",
        store=True,
        currency_field="currency_id",
    )

    @api.depends(
        "product_id",
        "product_uom_qty",
        "purchase_price",
        "price_subtotal",
        "product_id.extra_cost_total",
        "product_id.product_tmpl_id.extra_cost_total",
    )
    def _compute_artcasa_line_margin(self):
        for line in self:
            extra_unit = line.product_id.product_tmpl_id.extra_cost_total if line.product_id else 0.0
            line.extra_cost_unit = extra_unit
            line.extra_cost_total = extra_unit * line.product_uom_qty
            line.margin_after_extra = line.price_subtotal - (line.purchase_price * line.product_uom_qty) - line.extra_cost_total
