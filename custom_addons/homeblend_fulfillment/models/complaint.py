from odoo import fields, models


class HomeblendComplaint(models.Model):
    _name = "homeblend.complaint"
    _description = "شكوى مستأجر"
    _order = "date desc, id desc"

    name = fields.Char(string="الشكوى", required=True)
    partner_id = fields.Many2one(
        "res.partner",
        string="المستأجر",
        required=True,
        domain="[('is_tenant', '=', True)]",
        ondelete="cascade",
        index=True,
    )
    date = fields.Date(string="التاريخ", required=True, default=fields.Date.context_today)
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company)
    state = fields.Selection(
        [("open", "مفتوحة"), ("done", "مغلقة")],
        default="open",
        required=True,
    )
    notes = fields.Text(string="التفاصيل")
