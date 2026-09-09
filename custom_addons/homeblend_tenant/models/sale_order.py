from odoo import api, fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

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
