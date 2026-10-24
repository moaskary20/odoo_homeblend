from odoo import api, fields, models


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

    @api.onchange("purchase_order_id")
    def _onchange_purchase_order_id(self):
        if self.purchase_order_id:
            self.document_type = "purchase"
            self.partner_id = self.purchase_order_id.partner_id
            self.res_model = "purchase.order"
            self.res_id = self.purchase_order_id.id
