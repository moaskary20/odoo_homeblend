from odoo import api, fields, models, _
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = ["sale.order", "barcodes.barcode_events_mixin"]

    hb_barcode_input = fields.Char(string="مسح QR / باركود الصنف")

    def _hb_report_lang(self):
        """طباعة عروض الأسعار/أوامر البيع بالعربية حتى يكون PDF من اليمين لليسار."""
        self.ensure_one()
        Lang = self.env["res.lang"]
        if Lang._get_code("ar_001"):
            return "ar_001"
        partner_lang = self.partner_id.lang
        if partner_lang and Lang._get_data(code=partner_lang).direction == "rtl":
            return partner_lang
        return partner_lang or self.env.user.lang

    tenant_id = fields.Many2one(
        "res.partner",
        string="المستأجر",
        domain="[('is_tenant', '=', True)]",
        index=True,
        tracking=True,
        check_company=True,
    )
    tenant_contract_id = fields.Many2one(
        "homeblend.tenant.contract",
        string="عقد المستأجر",
        compute="_compute_tenant_contract_id",
        store=True,
        readonly=False,
    )
    commission_percent = fields.Float(related="tenant_contract_id.commission_percent")
    commission_base = fields.Selection(related="tenant_contract_id.commission_base")

    @api.depends("tenant_id", "company_id", "date_order")
    def _compute_tenant_contract_id(self):
        Contract = self.env["homeblend.tenant.contract"]
        for order in self:
            if order.tenant_id:
                order.tenant_contract_id = Contract.get_active_for_tenant(order.tenant_id, order.company_id)
            else:
                order.tenant_contract_id = False

    @api.onchange("partner_id")
    def _onchange_partner_set_tenant(self):
        if self.partner_id and self.partner_id.is_tenant and not self.tenant_id:
            self.tenant_id = self.partner_id

    @api.model_create_multi
    def create(self, vals_list):
        orders = super().create(vals_list)
        for order in orders:
            term = order.tenant_contract_id.payment_term_id
            if term and not order.payment_term_id:
                order.payment_term_id = term
        return orders

    def _prepare_invoice(self):
        vals = super()._prepare_invoice()
        vals["tenant_id"] = self.tenant_id.id
        vals["homeblend_contract_id"] = self.tenant_contract_id.id
        return vals

    def _create_invoices(self, grouped=False, final=False, date=None):
        moves = super()._create_invoices(grouped=grouped, final=final, date=date)
        moves._hb_split_bearing_invoice()
        return moves

    def on_barcode_scanned(self, barcode):
        self._hb_add_product_by_code(barcode)
        return True

    def action_hb_scan_product(self):
        self.ensure_one()
        if not self.hb_barcode_input:
            raise UserError(_("أدخل أو امسح كود الصنف أولاً."))
        self._hb_add_product_by_code(self.hb_barcode_input)
        self.hb_barcode_input = False
        return True

    def _hb_add_product_by_code(self, code):
        self.ensure_one()
        if self.state not in ("draft", "sent"):
            raise UserError(_("يمكن مسح الأصناف في أمر البيع قبل التأكيد فقط."))
        value = (code or "").strip()
        if not value:
            return
        Product = self.env["product.product"]
        product = Product.search([
            "|",
            ("barcode", "=", value),
            ("default_code", "=", value),
        ], limit=1)
        if not product:
            raise UserError(_("لا يوجد صنف بهذا الكود/الباركود: %s") % value)
        line = self.order_line.filtered(lambda l: l.product_id == product and not l.display_type)[:1]
        if line:
            line.product_uom_qty += 1
        else:
            self.env["sale.order.line"].create({
                "order_id": self.id,
                "product_id": product.id,
                "product_uom_qty": 1,
            })
