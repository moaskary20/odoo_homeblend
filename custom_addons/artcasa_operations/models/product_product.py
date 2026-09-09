from collections import defaultdict

from odoo import api, fields, models


class ProductProduct(models.Model):
    _inherit = "product.product"

    def _artcasa_blocking_qty(self):
        """Active salesperson reservations that make qty unavailable for sale."""
        if not self or "artcasa.stock.reservation" not in self.env:
            return {}
        now = fields.Datetime.now()
        domain = [
            ("product_id", "in", self.ids),
            ("state", "=", "reserved"),
            ("date_start", "<=", now),
            ("date_end", ">=", now),
        ]
        warehouse_id = self.env.context.get("warehouse_id")
        if warehouse_id:
            domain.append(("warehouse_id", "=", warehouse_id))
        grouped = self.env["artcasa.stock.reservation"]._read_group(domain, ["product_id"], ["quantity:sum"])
        return defaultdict(float, {product.id: qty for product, qty in grouped})

    def _compute_quantities_dict(self, lot_id, owner_id, package_id, from_date=False, to_date=False):
        res = super()._compute_quantities_dict(lot_id, owner_id, package_id, from_date, to_date)
        if self.env.context.get("skip_artcasa_reservation"):
            return res
        blocking = self._artcasa_blocking_qty()
        for product in self:
            qty = blocking.get(product.id, 0.0)
            if not qty or product.id not in res:
                continue
            uom = product.uom_id
            res[product.id]["free_qty"] = uom.round((res[product.id].get("free_qty") or 0.0) - qty)
            res[product.id]["virtual_available"] = uom.round(
                (res[product.id].get("virtual_available") or 0.0) - qty
            )
        return res
