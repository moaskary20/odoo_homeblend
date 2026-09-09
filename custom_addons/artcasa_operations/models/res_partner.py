from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    supplier_on_time_rate = fields.Float(string="الالتزام بالمواعيد %", compute="_compute_supplier_performance")
    supplier_late_po_count = fields.Integer(string="أوامر متأخرة", compute="_compute_supplier_performance")

    def _compute_supplier_performance(self):
        Purchase = self.env["purchase.order"]
        now = fields.Datetime.now()
        for partner in self:
            orders = Purchase.search([
                ("partner_id", "=", partner.id),
                ("state", "in", ["purchase", "done"]),
            ], limit=80)
            late = 0
            for po in orders:
                done = po.picking_ids.filtered(lambda p: p.state == "done" and p.picking_type_code == "incoming")
                planned = po.date_planned
                if not planned:
                    continue
                if done:
                    last = max(done.mapped("date_done"))
                    if last and last > planned:
                        late += 1
                elif planned < now:
                    late += 1
            partner.supplier_late_po_count = late
            partner.supplier_on_time_rate = ((len(orders) - late) / len(orders) * 100.0) if orders else 100.0
