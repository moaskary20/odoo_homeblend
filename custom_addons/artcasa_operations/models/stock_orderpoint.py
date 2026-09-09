from odoo import api, fields, models, _


class StockWarehouseOrderpoint(models.Model):
    _inherit = "stock.warehouse.orderpoint"

    @api.model
    def _cron_artcasa_low_stock(self):
        Activity = self.env["mail.activity"]
        for op in self.search([]):
            if op.qty_on_hand > op.product_min_qty:
                continue
            summary = _("حد المخزون: %s في %s") % (op.product_id.display_name, op.warehouse_id.display_name)
            if Activity.search([
                ("res_model", "=", "product.product"),
                ("res_id", "=", op.product_id.id),
                ("summary", "=", summary),
            ], limit=1):
                continue
            op.product_id.activity_schedule(
                "mail.mail_activity_data_todo",
                summary=summary,
                date_deadline=fields.Date.context_today(self),
            )
        return True
