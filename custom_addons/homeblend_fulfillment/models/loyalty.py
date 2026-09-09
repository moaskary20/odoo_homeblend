from odoo import models


class LoyaltyCard(models.Model):
    _inherit = ["loyalty.card", "mail.activity.mixin"]


class LoyaltyProgram(models.Model):
    _inherit = ["loyalty.program", "mail.thread", "mail.activity.mixin"]
