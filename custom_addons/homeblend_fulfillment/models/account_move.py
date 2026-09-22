from odoo import api, fields, models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    hb_delivery_date = fields.Date(string="تاريخ التسليم", copy=False)
    hb_delivered = fields.Boolean(string="تم التسليم", copy=False)

    def _hb_is_customer_product_line(self):
        self.ensure_one()
        move = self.move_id
        if not move or move.move_type not in ("out_invoice", "out_refund"):
            return False
        if getattr(move, "is_commission_invoice", False):
            return False
        return self.display_type == "product"

    def _hb_default_delivery_date(self):
        self.ensure_one()
        commitment = False
        if self.sale_line_ids:
            commitment = self.sale_line_ids[:1].order_id.commitment_date
        if commitment:
            return commitment.date()
        return self.move_id.invoice_date or fields.Date.context_today(self)

    @api.onchange("hb_delivered")
    def _onchange_hb_delivered(self):
        for line in self:
            if line.hb_delivered and not line.hb_delivery_date:
                line.hb_delivery_date = fields.Date.context_today(line)

    @api.onchange("product_id")
    def _onchange_hb_delivery_product(self):
        for line in self:
            if line._hb_is_customer_product_line() and not line.hb_delivery_date:
                line.hb_delivery_date = line._hb_default_delivery_date()

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        to_fill = lines.filtered(lambda l: l._hb_is_customer_product_line() and not l.hb_delivery_date)
        for line in to_fill:
            line.hb_delivery_date = line._hb_default_delivery_date()
        return lines

    def write(self, vals):
        res = super().write(vals)
        if vals.get("hb_delivered") and "hb_delivery_date" not in vals:
            missing = self.filtered(lambda l: l.hb_delivered and not l.hb_delivery_date)
            if missing:
                super(AccountMoveLine, missing).write(
                    {"hb_delivery_date": fields.Date.context_today(self)}
                )
        return res


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    def _prepare_invoice_line(self, **optional_values):
        vals = super()._prepare_invoice_line(**optional_values)
        commitment = self.order_id.commitment_date
        vals["hb_delivery_date"] = commitment.date() if commitment else fields.Date.context_today(self)
        vals["hb_delivered"] = False
        return vals
