from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    track_id = fields.Many2one("homeblend.order.track", compute="_compute_track_id", search="_search_track_id", export_string_translation=False)
    track_state = fields.Selection(related="track_id.state", string="تتبع الطلب")

    def _compute_track_id(self):
        Track = self.env["homeblend.order.track"]
        for order in self:
            order.track_id = Track.search([("sale_order_id", "=", order.id)], limit=1)

    def _search_track_id(self, operator, value):
        tracks = self.env["homeblend.order.track"].search([("id", operator, value)])
        return [("id", "in", tracks.mapped("sale_order_id").ids)]

    def action_confirm(self):
        res = super().action_confirm()
        Track = self.env["homeblend.order.track"]
        for order in self:
            track = Track.search([("sale_order_id", "=", order.id)], limit=1)
            if not track:
                track = Track.create({
                    "sale_order_id": order.id,
                    "state": "confirmed",
                })
            elif track.state == "draft":
                track.action_confirmed()
        return res

    def action_open_track(self):
        self.ensure_one()
        if not self.track_id:
            self.env["homeblend.order.track"].create({"sale_order_id": self.id})
            self.invalidate_recordset(["track_id"])
        return {
            "type": "ir.actions.act_window",
            "res_model": "homeblend.order.track",
            "res_id": self.track_id.id,
            "view_mode": "form",
            "target": "current",
        }
