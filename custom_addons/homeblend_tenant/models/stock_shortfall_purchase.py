# -*- coding: utf-8 -*-
"""تغطية تلقائية للمخزون السالب: أمر شراء + استلام بآخر سعر شراء."""

import logging

from odoo import _, api, fields, models
from odoo.tools import float_compare

_logger = logging.getLogger(__name__)


class ProductProduct(models.Model):
    _inherit = "product.product"

    def _hb_is_storable(self):
        self.ensure_one()
        if "is_storable" in self._fields:
            return bool(self.is_storable)
        return self.type == "product"

    def _hb_get_last_purchase_price(self, company):
        """آخر سعر شراء مؤكد، وإلا سعر المورد، وإلا التكلفة المعيارية."""
        self.ensure_one()
        company = company or self.env.company
        POL = self.env["purchase.order.line"].sudo()
        line = POL.search(
            [
                ("product_id", "=", self.id),
                ("order_id.company_id", "=", company.id),
                ("order_id.state", "in", ("purchase", "done")),
                ("product_qty", ">", 0),
            ],
            order="id desc",
            limit=1,
        )
        if line:
            # حوّل لوحدة المنتج إن لزم
            price = line.price_unit
            if line.product_uom and line.product_uom != self.uom_id:
                price = line.product_uom._compute_price(price, self.uom_id)
            return price
        seller = False
        if hasattr(self, "_select_seller"):
            seller = self._select_seller(quantity=1.0, uom_id=self.uom_id)
        if not seller:
            sellers = self.seller_ids.filtered(lambda s: not s.company_id or s.company_id == company)
            seller = sellers[:1]
        if seller:
            price = seller.price
            seller_uom = seller.product_uom_id if "product_uom_id" in seller._fields else seller.product_uom
            if seller_uom and seller_uom != self.uom_id:
                price = seller_uom._compute_price(price, self.uom_id)
            return price
        return self.with_company(company).standard_price or 0.0

    def _hb_get_replenish_vendor(self, company):
        """مورد التغطية: قائمة الموردين ثم آخر أمر شراء."""
        self.ensure_one()
        company = company or self.env.company
        sellers = self.seller_ids.filtered(lambda s: not s.company_id or s.company_id == company)
        if sellers:
            return sellers.sorted(key=lambda s: (s.sequence, s.id))[:1].partner_id
        POL = self.env["purchase.order.line"].sudo()
        line = POL.search(
            [
                ("product_id", "=", self.id),
                ("order_id.company_id", "=", company.id),
                ("order_id.state", "in", ("purchase", "done")),
            ],
            order="id desc",
            limit=1,
        )
        return line.order_id.partner_id if line else self.env["res.partner"]


class HbShortfallPurchaseMixin(models.AbstractModel):
    _name = "hb.shortfall.purchase.mixin"
    _description = "تغطية نقص المخزون بالشراء والاستلام"

    def _hb_warehouse_for_cover(self):
        raise NotImplementedError

    def _hb_shortfall_demand_lines(self):
        """أعد قائمة [(product, qty_in_product_uom), ...] للطلب الحالي."""
        raise NotImplementedError

    def _hb_already_covered_origins(self):
        self.ensure_one()
        return [self.name] if getattr(self, "name", None) else []

    def _hb_cover_stock_shortfall(self):
        """إنشاء أوامر شراء وتأكيدها واستلامها تلقائياً لنقص الكمية."""
        PurchaseOrder = self.env["purchase.order"].sudo()
        for record in self:
            company = record.company_id
            warehouse = record._hb_warehouse_for_cover()
            if not warehouse:
                continue
            demands = record._hb_shortfall_demand_lines()
            if not demands:
                continue
            # تجميع النقص حسب المنتج
            need_by_product = {}
            for product, qty in demands:
                if not product or not product._hb_is_storable():
                    continue
                need_by_product[product] = need_by_product.get(product, 0.0) + qty

            shortfalls = []  # (product, qty, vendor, price)
            for product, qty_needed in need_by_product.items():
                product = product.with_company(company).with_context(warehouse_id=warehouse.id)
                available = product.free_qty
                rounding = product.uom_id.rounding or 0.01
                shortfall = qty_needed - available
                if float_compare(shortfall, 0.0, precision_rounding=rounding) <= 0:
                    continue
                vendor = product._hb_get_replenish_vendor(company)
                if not vendor:
                    _logger.warning(
                        "HB shortfall: لا مورد للصنف %s — تُخطّى التغطية التلقائية",
                        product.display_name,
                    )
                    if hasattr(record, "message_post"):
                        record.message_post(
                            body=_(
                                "تعذّر إنشاء أمر شراء تلقائي للصنف %(product)s: لا يوجد مورد. "
                                "الرصيد المتاح %(avail)s والمطلوب %(need)s."
                            )
                            % {
                                "product": product.display_name,
                                "avail": available,
                                "need": qty_needed,
                            }
                        )
                    continue
                price = product._hb_get_last_purchase_price(company)
                shortfalls.append((product, shortfall, vendor, price))

            if not shortfalls:
                continue

            # تجميع حسب المورد
            by_vendor = {}
            for product, qty, vendor, price in shortfalls:
                by_vendor.setdefault(vendor, []).append((product, qty, price))

            origins = record._hb_already_covered_origins()
            origin = ", ".join(o for o in origins if o) or record.display_name

            # تجنّب التكرار إن وُجد أمر شراء مفتوح بنفس المصدر والمنتجات
            existing = PurchaseOrder.search(
                [
                    ("company_id", "=", company.id),
                    ("origin", "ilike", record.name or origin),
                    ("state", "in", ("draft", "sent", "to approve", "purchase", "done")),
                ],
                limit=20,
            )
            for vendor, items in by_vendor.items():
                if existing.filtered(lambda po: po.partner_id == vendor and record.name and record.name in (po.origin or "")):
                    # حدث الاستلام إن كان معلّقاً
                    for po in existing.filtered(lambda p: p.partner_id == vendor):
                        record._hb_validate_purchase_receipts(po)
                    continue
                po_vals = {
                    "partner_id": vendor.id,
                    "company_id": company.id,
                    "currency_id": company.currency_id.id,
                    "origin": origin,
                    "picking_type_id": warehouse.in_type_id.id,
                    "dest_address_id": False,
                }
                if "date_order" in PurchaseOrder._fields:
                    po_vals["date_order"] = fields.Datetime.now()
                order_lines = []
                for product, qty, price in items:
                    line_vals = {
                        "product_id": product.id,
                        "name": product.display_name,
                        "product_qty": qty,
                        "product_uom": product.uom_id.id,
                        "price_unit": price,
                        "date_planned": fields.Datetime.now(),
                    }
                    order_lines.append((0, 0, line_vals))
                po_vals["order_line"] = order_lines
                po = PurchaseOrder.create(po_vals)
                po.button_confirm()
                record._hb_validate_purchase_receipts(po)
                if hasattr(record, "message_post"):
                    record.message_post(
                        body=_(
                            "تغطية مخزون تلقائية: أمر شراء %(po)s للمورد %(vendor)s "
                            "بسعر آخر شراء حتى الاستلام."
                        )
                        % {"po": po.name, "vendor": vendor.display_name}
                    )

    def _hb_validate_purchase_receipts(self, purchase_orders):
        """تأكيد كميات الاستلام والتحقق فوراً."""
        pickings = purchase_orders.mapped("picking_ids").filtered(
            lambda p: p.state not in ("done", "cancel") and p.picking_type_code == "incoming"
        )
        for picking in pickings:
            picking = picking.sudo()
            if picking.state == "draft":
                picking.action_confirm()
            for move in picking.move_ids:
                if move.state in ("done", "cancel"):
                    continue
                qty = move.product_uom_qty
                if "quantity" in move._fields:
                    move.quantity = qty
            try:
                picking.with_context(
                    cancel_backorder=True,
                    skip_backorder=True,
                    skip_sms=True,
                    skip_sanity_check=True,
                ).button_validate()
            except Exception as exc:
                _logger.exception("HB shortfall: فشل استلام %s: %s", picking.name, exc)
                try:
                    picking.with_context(cancel_backorder=True)._action_done()
                except Exception as exc2:
                    purchase_orders.message_post(
                        body=_("تعذّر إتمام الاستلام التلقائي لـ %(picking)s: %(err)s")
                        % {"picking": picking.name, "err": "%s / %s" % (exc, exc2)}
                    )


class PosOrder(models.Model):
    _inherit = ["pos.order", "hb.shortfall.purchase.mixin"]

    def _hb_warehouse_for_cover(self):
        self.ensure_one()
        warehouse = self.config_id.warehouse_id
        if warehouse:
            return warehouse
        picking_type = self.config_id.picking_type_id
        return picking_type.warehouse_id if picking_type else self.env["stock.warehouse"]

    def _hb_shortfall_demand_lines(self):
        self.ensure_one()
        result = []
        for line in self.lines:
            product = line.product_id
            if not product or line.qty <= 0:
                continue
            # المرتجعات (كمية سالبة) لا تحتاج تغطية شراء
            result.append((product, line.qty))
        return result

    def _create_order_picking(self):
        # غطِّ النقص قبل صرف المخزون حتى يُستلم بآخر سعر شراء
        for order in self:
            if order.is_refund:
                continue
            try:
                order._hb_cover_stock_shortfall()
            except Exception as exc:
                _logger.exception("HB shortfall POS %s: %s", order.name, exc)
                order.message_post(
                    body=_("تعذّرت التغطية التلقائية بالشراء: %s") % str(exc)
                )
        return super()._create_order_picking()


class SaleOrder(models.Model):
    _inherit = ["sale.order", "hb.shortfall.purchase.mixin"]

    def _hb_warehouse_for_cover(self):
        self.ensure_one()
        return self.warehouse_id

    def _hb_shortfall_demand_lines(self):
        self.ensure_one()
        result = []
        for line in self.order_line.filtered(lambda l: not l.display_type):
            product = line.product_id
            if not product:
                continue
            qty = line.product_uom._compute_quantity(line.product_uom_qty, product.uom_id)
            if qty <= 0:
                continue
            result.append((product, qty))
        return result

    def action_confirm(self):
        for order in self:
            try:
                order._hb_cover_stock_shortfall()
            except Exception as exc:
                _logger.exception("HB shortfall SO %s: %s", order.name, exc)
                order.message_post(
                    body=_("تعذّرت التغطية التلقائية بالشراء: %s") % str(exc)
                )
        return super().action_confirm()
