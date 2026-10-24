from odoo import fields, models


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    purchase_document_ids = fields.One2many("homeblend.document", "purchase_order_id", string="مستندات الشراء")
    purchase_document_count = fields.Integer(compute="_compute_purchase_document_count")

    def _compute_purchase_document_count(self):
        for order in self:
            order.purchase_document_count = len(order.purchase_document_ids)

    def action_view_purchase_documents(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "مستندات المشتريات",
            "res_model": "homeblend.document",
            "view_mode": "list,form",
            "domain": [("purchase_order_id", "=", self.id)],
            "context": {
                "default_document_type": "purchase",
                "default_purchase_order_id": self.id,
                "default_partner_id": self.partner_id.id,
            },
        }
