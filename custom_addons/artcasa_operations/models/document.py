from odoo import api, fields, models, _


class HomeblendDocument(models.Model):
    _inherit = "homeblend.document"

    document_type = fields.Selection(
        selection_add=[("purchase", "مشتريات")],
        ondelete={"purchase": "set default"},
    )
    purchase_order_id = fields.Many2one(
        "purchase.order",
        string="أمر الشراء",
        tracking=True,
        ondelete="set null",
    )

    @api.model_create_multi
    def create(self, vals_list):
        orders = self.env["purchase.order"].browse([
            vals["purchase_order_id"] for vals in vals_list if vals.get("purchase_order_id")
        ])
        for vals in vals_list:
            order_id = vals.get("purchase_order_id")
            if not order_id:
                continue
            order = orders.browse(order_id)
            vals["document_type"] = "purchase"
            vals.setdefault("partner_id", order.partner_id.id)
            vals.setdefault("company_id", order.company_id.id)
            vals["res_model"] = "purchase.order"
            vals["res_id"] = order.id
            if not vals.get("name"):
                vals["name"] = vals.get("datas_fname") or _("ملف أمر الشراء")
        return super().create(vals_list)

    @api.onchange("purchase_order_id")
    def _onchange_purchase_order_id(self):
        if self.purchase_order_id:
            self.document_type = "purchase"
            self.partner_id = self.purchase_order_id.partner_id
            self.res_model = "purchase.order"
            self.res_id = self.purchase_order_id.id
