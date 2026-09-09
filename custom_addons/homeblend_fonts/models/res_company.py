from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    # خط تخطيط المستندات في أودو افتراضه Lato، وهو ما تستخدمه قوالب PDF
    # عبر styles_company_report، فنجعل الافتراضي Tajawal للشركات الجديدة.
    font = fields.Selection(default="Tajawal")
