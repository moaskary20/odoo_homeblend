from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    artcasa_margin_include_tax = fields.Boolean(
        string="احتساب صافي الربح بعد الضريبة",
        help="إذا فُعّل يُحسب صافي الربح من إجمالي الفاتورة بعد الضريبة بدل المبلغ غير شامل الضريبة.",
    )
