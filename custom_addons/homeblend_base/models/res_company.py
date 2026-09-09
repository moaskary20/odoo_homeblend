from odoo import api, fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    is_homeblend = fields.Boolean(
        string="شركة Home Blend",
        compute="_compute_brand_flags",
        store=True,
    )
    is_artcasa = fields.Boolean(
        string="شركة Art Casa",
        compute="_compute_brand_flags",
        store=True,
    )

    @api.depends("name")
    def _compute_brand_flags(self):
        for company in self:
            name = (company.name or "").strip().lower()
            company.is_homeblend = "home blend" in name or name == "homeblend"
            company.is_artcasa = "art casa" in name or name == "artcasa"
