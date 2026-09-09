from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    tenant_contract_ids = fields.One2many("homeblend.tenant.contract", "tenant_id", string="عقود المستأجر")
    tenant_contract_count = fields.Integer(compute="_compute_tenant_contract_count")

    tenant_invoice_count = fields.Integer(compute="_compute_tenant_stats")
    tenant_sale_count = fields.Integer(compute="_compute_tenant_stats")
    tenant_unpaid_count = fields.Integer(compute="_compute_tenant_stats")
    tenant_activity_count = fields.Integer(compute="_compute_tenant_stats")
    tenant_payment_count = fields.Integer(compute="_compute_tenant_stats")
    tenant_refund_count = fields.Integer(compute="_compute_tenant_stats")
    tenant_last_deal_date = fields.Datetime(string="آخر تعامل", compute="_compute_tenant_stats")

    vendor_purchase_order_ids = fields.One2many("purchase.order", "partner_id", string="أوامر الشراء")
    vendor_payment_count = fields.Integer(compute="_compute_vendor_file")
    vendor_last_purchase_date = fields.Datetime(string="آخر أمر شراء", compute="_compute_vendor_file")
    vendor_last_bill_date = fields.Date(string="آخر فاتورة مورد", compute="_compute_vendor_file")

    def _compute_tenant_contract_count(self):
        data = self.env["homeblend.tenant.contract"]._read_group(
            [("tenant_id", "in", self.ids)],
            ["tenant_id"],
            ["__count"],
        )
        mapped = {tenant.id: count for tenant, count in data}
        for partner in self:
            partner.tenant_contract_count = mapped.get(partner.id, 0)

    def _compute_tenant_stats(self):
        Move = self.env["account.move"]
        Sale = self.env["sale.order"]
        Payment = self.env["account.payment"]
        for partner in self:
            invoices = Move.search([
                ("tenant_id", "=", partner.id),
                ("move_type", "in", ["out_invoice", "out_refund"]),
            ])
            sales_invoices = invoices.filtered(lambda m: m.move_type == "out_invoice")
            refunds = invoices.filtered(lambda m: m.move_type == "out_refund")
            unpaid = sales_invoices.filtered(
                lambda m: m.state == "posted" and m.payment_state in ("not_paid", "partial")
            )
            last_sale = Sale.search([("tenant_id", "=", partner.id)], order="date_order desc", limit=1)
            partner.tenant_invoice_count = len(sales_invoices)
            partner.tenant_refund_count = len(refunds)
            partner.tenant_unpaid_count = len(unpaid)
            partner.tenant_sale_count = Sale.search_count([("tenant_id", "=", partner.id)])
            partner.tenant_last_deal_date = last_sale.date_order if last_sale else False
            partner.tenant_activity_count = self.env["mail.activity"].search_count([
                ("res_model", "=", "res.partner"),
                ("res_id", "=", partner.id),
            ])
            partner.tenant_payment_count = Payment.search_count([
                ("reconciled_invoice_ids", "in", invoices.ids),
            ]) if invoices else 0

    def _compute_vendor_file(self):
        Purchase = self.env["purchase.order"]
        Move = self.env["account.move"]
        Payment = self.env["account.payment"]
        for partner in self:
            last_po = Purchase.search([("partner_id", "=", partner.id)], order="date_order desc", limit=1)
            last_bill = Move.search([
                ("partner_id", "=", partner.id),
                ("move_type", "in", ["in_invoice", "in_refund"]),
            ], order="invoice_date desc, id desc", limit=1)
            partner.vendor_last_purchase_date = last_po.date_order if last_po else False
            partner.vendor_last_bill_date = last_bill.invoice_date if last_bill else False
            partner.vendor_payment_count = Payment.search_count([
                ("partner_id", "=", partner.id),
                ("partner_type", "=", "supplier"),
            ])

    def action_view_tenant_contracts(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "عقود المستأجر",
            "res_model": "homeblend.tenant.contract",
            "view_mode": "list,form",
            "domain": [("tenant_id", "=", self.id)],
            "context": {"default_tenant_id": self.id, "default_is_tenant": True},
        }

    def action_view_tenant_sales(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "مبيعات المستأجر",
            "res_model": "sale.order",
            "view_mode": "list,form",
            "domain": [("tenant_id", "=", self.id)],
            "context": {"default_tenant_id": self.id},
        }

    def action_view_tenant_invoices(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "فواتير المستأجر",
            "res_model": "account.move",
            "view_mode": "list,form",
            "domain": [("tenant_id", "=", self.id), ("move_type", "=", "out_invoice")],
            "context": {"default_tenant_id": self.id, "default_move_type": "out_invoice"},
        }

    def action_view_tenant_unpaid(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "متأخرات التحصيل",
            "res_model": "account.move",
            "view_mode": "list,form",
            "domain": [
                ("tenant_id", "=", self.id),
                ("move_type", "=", "out_invoice"),
                ("state", "=", "posted"),
                ("payment_state", "in", ["not_paid", "partial"]),
            ],
        }

    def action_view_tenant_notifications(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "تنبيهات المستأجر",
            "res_model": "mail.activity",
            "view_mode": "list,form",
            "domain": [("res_model", "=", "res.partner"), ("res_id", "=", self.id)],
            "context": {"default_res_model": "res.partner", "default_res_id": self.id},
        }

    def action_view_tenant_payments(self):
        self.ensure_one()
        invoices = self.env["account.move"].search([
            ("tenant_id", "=", self.id),
            ("move_type", "in", ["out_invoice", "out_refund"]),
        ])
        payments = self.env["account.payment"].search([
            ("reconciled_invoice_ids", "in", invoices.ids),
        ])
        return {
            "type": "ir.actions.act_window",
            "name": "تحصيلات المستأجر",
            "res_model": "account.payment",
            "view_mode": "list,form",
            "domain": [("id", "in", payments.ids)],
        }

    def action_view_tenant_refunds(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "إشعارات المستأجر",
            "res_model": "account.move",
            "view_mode": "list,form",
            "domain": [("tenant_id", "=", self.id), ("move_type", "=", "out_refund")],
            "context": {"default_tenant_id": self.id, "default_move_type": "out_refund"},
        }

    def action_view_vendor_payments(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "مدفوعات المورد",
            "res_model": "account.payment",
            "view_mode": "list,form",
            "domain": [("partner_id", "=", self.id), ("partner_type", "=", "supplier")],
            "context": {
                "default_partner_id": self.id,
                "default_partner_type": "supplier",
                "default_payment_type": "outbound",
            },
        }
