from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    tenant_kpi_sales = fields.Monetary(string="حجم المبيعات", compute="_compute_tenant_kpi", currency_field="currency_id")
    tenant_kpi_returns = fields.Integer(string="عدد المرتجعات", compute="_compute_tenant_kpi")
    tenant_kpi_delayed = fields.Integer(string="طلبات متأخرة", compute="_compute_tenant_kpi")
    tenant_kpi_unpaid = fields.Monetary(string="متأخرات التحصيل", compute="_compute_tenant_kpi", currency_field="currency_id")
    tenant_kpi_complaints = fields.Integer(string="عدد الشكاوى", compute="_compute_tenant_kpi")
    tenant_kpi_on_time = fields.Float(string="الالتزام بالتسليم %", compute="_compute_tenant_kpi")
    tenant_kpi_satisfaction = fields.Float(string="رضا العملاء", compute="_compute_tenant_kpi")
    tenant_kpi_quality = fields.Float(string="جودة الخدمة", compute="_compute_tenant_kpi")
    tenant_kpi_speed = fields.Float(string="سرعة التنفيذ %", compute="_compute_tenant_kpi")
    tenant_kpi_collection_speed = fields.Float(string="سرعة التحصيل %", compute="_compute_tenant_kpi")
    tenant_kpi_contract_ok = fields.Boolean(string="ملتزم بالعقد", compute="_compute_tenant_kpi")
    tenant_score = fields.Float(string="تقييم الأداء", compute="_compute_tenant_kpi")
    complaint_ids = fields.One2many("homeblend.complaint", "partner_id", string="الشكاوى")

    def _compute_tenant_kpi(self):
        Track = self.env["homeblend.order.track"]
        Move = self.env["account.move"]
        for partner in self:
            tracks = Track.search([("tenant_id", "=", partner.id)])
            partner.tenant_kpi_returns = len(tracks.filtered(lambda t: t.state == "returned"))
            partner.tenant_kpi_delayed = len(tracks.filtered(lambda t: t.state == "delayed"))
            invoices = Move.search([
                ("tenant_id", "=", partner.id),
                ("move_type", "=", "out_invoice"),
                ("state", "=", "posted"),
                ("is_commission_invoice", "=", False),
            ])
            partner.tenant_kpi_sales = sum(invoices.mapped("amount_untaxed"))
            unpaid = invoices.filtered(lambda i: i.payment_state in ("not_paid", "partial"))
            partner.tenant_kpi_unpaid = sum(unpaid.mapped("amount_residual"))
            partner.tenant_kpi_complaints = self.env["homeblend.complaint"].search_count([
                ("partner_id", "=", partner.id),
            ])
            relevant = tracks.filtered(lambda t: t.state in ("completed", "delivered", "delayed"))
            on_time = tracks.filtered(lambda t: t.state in ("completed", "delivered"))
            partner.tenant_kpi_on_time = (len(on_time) / len(relevant) * 100.0) if relevant else 100.0
            partner.tenant_kpi_satisfaction = max(0.0, 100.0 - partner.tenant_kpi_complaints * 10)
            partner.tenant_kpi_quality = partner.tenant_kpi_satisfaction
            partner.tenant_kpi_speed = partner.tenant_kpi_on_time
            if partner.tenant_kpi_sales:
                partner.tenant_kpi_collection_speed = max(
                    0.0,
                    100.0 - min(100.0, (partner.tenant_kpi_unpaid / partner.tenant_kpi_sales) * 100.0),
                )
            else:
                partner.tenant_kpi_collection_speed = 100.0
            has_active = bool(self.env["homeblend.tenant.contract"].search_count([
                ("tenant_id", "=", partner.id),
                ("state", "=", "active"),
            ]))
            partner.tenant_kpi_contract_ok = has_active
            score = 100.0
            score -= partner.tenant_kpi_delayed * 5
            score -= partner.tenant_kpi_returns * 8
            score -= partner.tenant_kpi_complaints * 6
            if not has_active:
                score -= 10
            if partner.tenant_kpi_sales:
                score -= min(20, (partner.tenant_kpi_unpaid / partner.tenant_kpi_sales) * 20)
            partner.tenant_score = max(0.0, min(100.0, score))
