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
    payment_term_id = fields.Many2one(
        "account.payment.term",
        related="tenant_contract_id.payment_term_id",
        string="شروط الدفع / الأقساط",
    )
    paper_invoice = fields.Binary(string="الفاتورة الورقية", attachment=True, copy=False)
    paper_invoice_filename = fields.Char(string="اسم ملف الفاتورة الورقية", copy=False)

    @api.model
    def _load_pos_data_fields(self, config):
        fields = super()._load_pos_data_fields(config)
        if not fields:
            return fields
        extra = ["tenant_id", "tenant_contract_id", "paper_invoice", "paper_invoice_filename"]
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
            if contract.payment_term_id:
                vals["invoice_payment_term_id"] = contract.payment_term_id.id
        return vals

    def _create_invoice(self, move_vals):
        invoice = super()._create_invoice(move_vals)
        order = self[:1]
        paper_vals = {}
        if order.paper_invoice and not invoice.paper_invoice:
            paper_vals["paper_invoice"] = order.paper_invoice
            paper_vals["paper_invoice_filename"] = order.paper_invoice_filename
        if paper_vals:
            invoice.write(paper_vals)
        return invoice

    def _sync_paper_invoice_to_move(self):
        for order in self:
            move = order.account_move
            if not move or not order.paper_invoice:
                continue
            if move.paper_invoice == order.paper_invoice:
                continue
            move.write({
                "paper_invoice": order.paper_invoice,
                "paper_invoice_filename": order.paper_invoice_filename,
            })
        return True

    def _process_saved_order(self, draft):
        if self.partner_id or self.tenant_contract_id:
            self.to_invoice = True
        if self.tenant_contract_id and not self.tenant_id:
            self.tenant_id = self.tenant_contract_id.tenant_id
        res = super()._process_saved_order(draft)
        self._sync_paper_invoice_to_move()
        return res

    def write(self, vals):
        res = super().write(vals)
        if "paper_invoice" in vals or "paper_invoice_filename" in vals:
            self._sync_paper_invoice_to_move()
        return res


class PosSession(models.Model):
    _inherit = "pos.session"

    @api.model
    def _load_pos_data_models(self, config):
        models = super()._load_pos_data_models(config)
        extra = ["homeblend.tenant.contract", "account.payment.term"]
        for model in extra:
            if model not in models:
                models.append(model)
        return models


class AccountPaymentTerm(models.Model):
    _inherit = ["account.payment.term", "pos.load.mixin"]

    @api.model
    def _load_pos_data_domain(self, data, config):
        contract_ids = [row["payment_term_id"] for row in data.get("homeblend.tenant.contract", []) if row.get("payment_term_id")]
        return [("id", "in", contract_ids)] if contract_ids else [("id", "=", False)]

    @api.model
    def _load_pos_data_fields(self, config):
        return ["name", "note"]


class ResPartner(models.Model):
    _inherit = "res.partner"

    @api.model
    def _load_pos_data_fields(self, config):
        fields = super()._load_pos_data_fields(config)
        if "is_tenant" not in fields:
            fields = list(fields) + ["is_tenant"]
        return fields
