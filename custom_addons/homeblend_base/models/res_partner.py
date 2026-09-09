from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    is_tenant = fields.Boolean(string="مستأجر Home Blend")
    commercial_register = fields.Char(string="السجل التجاري")
    tax_id_number = fields.Char(string="الرقم الضريبي")
    responsible_ids = fields.Many2many(
        "res.partner",
        "homeblend_partner_responsible_rel",
        "partner_id",
        "responsible_id",
        string="المسؤولون",
        domain="[('is_company', '=', False)]",
    )
    branch_ids = fields.One2many("res.partner", "parent_id", string="الفروع")
    vendor_product_ids = fields.One2many("product.supplierinfo", "partner_id", string="منتجات المورد")
    guarantee_ids = fields.One2many("homeblend.partner.guarantee", "partner_id", string="الضمانات")
    tenant_score = fields.Float(string="تقييم الأداء", digits=(16, 2))
    credit_limit_amount = fields.Monetary(string="الحد الائتماني", currency_field="currency_id")
    supplier_lead_days = fields.Integer(string="مدة التوريد (أيام)")
    supplier_quality_score = fields.Float(string="تقييم جودة المورد", digits=(16, 2))

    def write(self, vals):
        res = super().write(vals)
        if "credit_limit_amount" in vals:
            for partner in self:
                if partner.credit_limit_amount:
                    super(ResPartner, partner.sudo()).write({"credit_limit": partner.credit_limit_amount})
        return res


class HomeblendPartnerGuarantee(models.Model):
    _name = "homeblend.partner.guarantee"
    _description = "ضمان شريك"

    partner_id = fields.Many2one("res.partner", required=True, ondelete="cascade")
    name = fields.Char(string="الضمان", required=True)
    amount = fields.Monetary(string="القيمة")
    currency_id = fields.Many2one(related="partner_id.currency_id")
    date_start = fields.Date(string="من")
    date_end = fields.Date(string="إلى")
    notes = fields.Text(string="ملاحظات")
