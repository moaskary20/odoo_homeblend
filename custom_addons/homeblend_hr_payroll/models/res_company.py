from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    payroll_journal_id = fields.Many2one(
        "account.journal",
        string="يومية الرواتب",
        domain="[('company_id', '=', id)]",
    )
    payroll_expense_account_id = fields.Many2one(
        "account.account",
        string="حساب مصروف الراتب",
        domain="[('account_type', '=', 'expense')]",
        check_company=True,
    )
    payroll_payable_account_id = fields.Many2one(
        "account.account",
        string="حساب صافي الراتب المستحق",
        domain="[('account_type', '=', 'liability_payable')]",
        check_company=True,
    )
    payroll_insurance_account_id = fields.Many2one(
        "account.account",
        string="حساب التأمينات المستحقة",
        domain="[('account_type', '=', 'liability_payable')]",
        check_company=True,
    )
    payroll_tax_account_id = fields.Many2one(
        "account.account",
        string="حساب ضريبة كسب العمل",
        domain="[('account_type', '=', 'liability_payable')]",
        check_company=True,
    )
