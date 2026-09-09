from odoo import api, fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    extra_cost_freight = fields.Monetary(string="تكلفة الشحن الداخلي", currency_field="currency_id")
    extra_cost_shipping = fields.Monetary(string="تكلفة الشحن الخارجي", currency_field="currency_id")
    extra_cost_other = fields.Monetary(string="تكاليف إضافية أخرى", currency_field="currency_id")
    extra_cost_total = fields.Monetary(
        string="إجمالي التكاليف الإضافية",
        compute="_compute_extra_cost_total",
        store=True,
        currency_field="currency_id",
    )
    origin_country_id = fields.Many2one("res.country", string="بلد المنشأ")
    brand_name = fields.Char(string="العلامة التجارية")
    product_group = fields.Char(string="المجموعة")
    min_stock_qty = fields.Float(string="الحد الأدنى للمخزون")
    max_stock_qty = fields.Float(string="الحد الأقصى للمخزون")
    qr_payload = fields.Char(string="QR / باركود", compute="_compute_qr_payload")
    actual_cost = fields.Monetary(
        string="التكلفة الفعلية",
        compute="_compute_actual_cost",
        currency_field="currency_id",
    )
    net_profit_unit = fields.Monetary(
        string="صافي الربح للوحدة",
        compute="_compute_actual_cost",
        currency_field="currency_id",
    )
    margin_percent_unit = fields.Float(string="نسبة الربح %", compute="_compute_actual_cost")
    main_seller_id = fields.Many2one("res.partner", string="المورد", compute="_compute_main_seller")

    @api.depends("extra_cost_freight", "extra_cost_shipping", "extra_cost_other")
    def _compute_extra_cost_total(self):
        for product in self:
            product.extra_cost_total = (
                product.extra_cost_freight + product.extra_cost_shipping + product.extra_cost_other
            )

    @api.depends("barcode", "default_code")
    def _compute_qr_payload(self):
        for product in self:
            product.qr_payload = product.barcode or product.default_code or ""

    @api.depends("standard_price", "extra_cost_total", "list_price")
    def _compute_actual_cost(self):
        for product in self:
            product.actual_cost = product.standard_price + product.extra_cost_total
            product.net_profit_unit = product.list_price - product.actual_cost
            product.margin_percent_unit = (
                product.net_profit_unit / product.list_price * 100.0 if product.list_price else 0.0
            )

    @api.depends("seller_ids.partner_id")
    def _compute_main_seller(self):
        for product in self:
            product.main_seller_id = product.seller_ids[:1].partner_id

    def write(self, vals):
        res = super().write(vals)
        if {"min_stock_qty", "max_stock_qty"} & set(vals):
            self._sync_orderpoints()
        return res

    def _sync_orderpoints(self):
        Orderpoint = self.env["stock.warehouse.orderpoint"]
        for product in self:
            if not product.product_variant_id:
                continue
            ops = Orderpoint.search([("product_id", "=", product.product_variant_id.id)])
            for op in ops:
                updates = {}
                if product.min_stock_qty:
                    updates["product_min_qty"] = product.min_stock_qty
                if product.max_stock_qty:
                    updates["product_max_qty"] = product.max_stock_qty
                if updates:
                    op.write(updates)
