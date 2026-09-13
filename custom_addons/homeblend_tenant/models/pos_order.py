from odoo import api, fields, models


class PosOrder(models.Model):
    _inherit = "pos.order"

    tenant_id = fields.Many2one(
        "res.partner",
        string="المستأجر",
        domain="[('is_tenant', '=', True)]",
        index=True,
        check_company=True,
    )
    tenant_contract_id = fields.Many2one(
        "homeblend.tenant.contract",
        string="عقد البيع",
        domain="[('state', '=', 'active'), ('company_id', '=', company_id)]",
        index=True,
        check_company=True,
    )
    commission_percent = fields.Float(related="tenant_contract_id.commission_percent")
    commission_base = fields.Selection(related="tenant_contract_id.commission_base")

    @api.model
    def _load_pos_data_fields(self, config):
        fields = super()._load_pos_data_fields(config)
        if not fields:
            return fields
        extra = ["tenant_id", "tenant_contract_id"]
        return list(dict.fromkeys(list(fields) + extra))

    @api.onchange("tenant_contract_id")
    def _onchange_tenant_contract(self):
        if self.tenant_contract_id:
            self.tenant_id = self.tenant_contract_id.tenant_id
            self.to_invoice = True
            if not self.partner_id:
                self.partner_id = self.tenant_contract_id.tenant_id

    @api.onchange("partner_id")
    def _onchange_partner_set_tenant_contract(self):
        if self.partner_id and self.partner_id.is_tenant:
            self.tenant_id = self.partner_id
            contract = self.env["homeblend.tenant.contract"].get_active_for_tenant(
                self.partner_id, self.company_id
            )
            if contract:
                self.tenant_contract_id = contract
                self.to_invoice = True

    def _prepare_invoice_vals(self):
        vals = super()._prepare_invoice_vals()
        contract = self[:1].tenant_contract_id
        tenant = self[:1].tenant_id or (contract.tenant_id if contract else False)
        if tenant:
            vals["tenant_id"] = tenant.id
        if contract:
            vals["homeblend_contract_id"] = contract.id
        return vals

    def _process_saved_order(self, draft):
        if self.tenant_contract_id:
            self.to_invoice = True
            if not self.tenant_id:
                self.tenant_id = self.tenant_contract_id.tenant_id
        return super()._process_saved_order(draft)


class PosSession(models.Model):
    _inherit = "pos.session"

    @api.model
    def _load_pos_data_models(self, config):
        models = super()._load_pos_data_models(config)
        if "homeblend.tenant.contract" not in models:
            models.append("homeblend.tenant.contract")
        return models


class ResPartner(models.Model):
    _inherit = "res.partner"

    @api.model
    def _load_pos_data_fields(self, config):
        fields = super()._load_pos_data_fields(config)
        if "is_tenant" not in fields:
            fields = list(fields) + ["is_tenant"]
        return fields
