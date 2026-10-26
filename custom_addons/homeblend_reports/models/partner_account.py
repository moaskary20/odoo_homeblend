from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.fields import Command


class HomeblendPartnerAccountWizard(models.TransientModel):
    _name = "homeblend.partner.account.wizard"
    _description = "إضافة عميل أو مورد إلى شجرة الحسابات"

    kind = fields.Selection(
        [("customer", "عميل"), ("supplier", "مورد")],
        string="النوع",
        required=True,
        default="customer",
    )
    name = fields.Char(string="الاسم", required=True)
    phone = fields.Char(string="الهاتف")
    vat = fields.Char(string="الرقم الضريبي")
    partner_id = fields.Many2one("res.partner", string="شريك موجود")
    company_id = fields.Many2one(
        "res.company",
        string="الشركة",
        required=True,
        default=lambda self: self._default_company(),
    )

    @api.model
    def _default_company(self):
        company = self.env["res.company"].search([("name", "ilike", "home"), ("name", "ilike", "blend")], limit=1)
        return company or self.env.company

    @api.onchange("partner_id")
    def _onchange_partner_id(self):
        partner = self.partner_id
        if not partner:
            return
        self.name = partner.name
        self.phone = partner.phone
        self.vat = partner.vat

    def action_add(self):
        self.ensure_one()
        company = self.company_id
        is_customer = self.kind == "customer"
        parent_code = "HB12010" if is_customer else "HB22003"
        account_type = "asset_receivable" if is_customer else "liability_payable"
        section = "bs_receivable" if is_customer else "bs_payable"
        property_field = "property_account_receivable_id" if is_customer else "property_account_payable_id"
        Account = self.env["account.account"].sudo().with_company(company)
        parent = Account.search([("code", "=", parent_code), ("company_ids", "in", company.id)], limit=1)
        if not parent:
            raise UserError(_("حساب %s غير موجود في شجرة هوم بليند. حدّث تطبيق التقارير أولاً.") % parent_code)

        partner = self.partner_id.sudo()
        if partner:
            updates = {}
            if is_customer and not partner.customer_rank:
                updates["customer_rank"] = 1
            if not is_customer and not partner.supplier_rank:
                updates["supplier_rank"] = 1
            if self.phone and not partner.phone:
                updates["phone"] = self.phone
            if self.vat and not partner.vat:
                updates["vat"] = self.vat
            if self.name and partner.name != self.name:
                updates["name"] = self.name
            if updates:
                partner.write(updates)
        else:
            partner = self.env["res.partner"].sudo().create({
                "name": self.name,
                "phone": self.phone,
                "vat": self.vat,
                "customer_rank": 1 if is_customer else 0,
                "supplier_rank": 0 if is_customer else 1,
            })

        account = Account.search([
            ("hb_partner_id", "=", partner.id),
            ("account_type", "=", account_type),
            ("company_ids", "in", company.id),
        ], limit=1)
        if not account:
            account = Account.create({
                "name": self.name,
                "code": self._next_child_code(Account, parent_code),
                "account_type": account_type,
                "reconcile": True,
                "company_ids": [Command.set([company.id])],
                "hb_chart": True,
                "hb_statement_section": section,
                "hb_partner_id": partner.id,
            })
        elif account.name != self.name:
            account.name = self.name
        partner.with_company(company).sudo().write({property_field: account.id})
        return {
            "type": "ir.actions.act_window",
            "name": account.display_name,
            "res_model": "account.account",
            "res_id": account.id,
            "view_mode": "form",
            "target": "current",
        }

    def _next_child_code(self, accounts, parent_code):
        taken = accounts.search([("code", "=like", parent_code + "%")]).mapped("code")
        sequence = 0
        for code in taken:
            tail = (code or "")[len(parent_code):]
            if tail.isdigit():
                sequence = max(sequence, int(tail))
        return "%s%03d" % (parent_code, sequence + 1)
