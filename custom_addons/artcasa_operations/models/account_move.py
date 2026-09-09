from odoo import api, fields, models, _
from odoo.fields import Command


class AccountMove(models.Model):
    _inherit = "account.move"

    artcasa_split_role = fields.Selection(
        [("customer", "حصة العميل"), ("project", "حصة المشروع")],
        string="نوع تقسيم Art Casa",
        copy=False,
    )
    artcasa_split_source_id = fields.Many2one("account.move", string="الفاتورة المقسمة منها", copy=False)
    artcasa_project_id = fields.Many2one("project.project", string="مشروع Art Casa", copy=True)

    @api.onchange("artcasa_project_id")
    def _onchange_artcasa_project(self):
        """مستخلصات المشروع تتبع دفعات العقد المتفق عليها."""
        for move in self:
            if move.artcasa_project_id.payment_term_id:
                move.invoice_payment_term_id = move.artcasa_project_id.payment_term_id

    def _artcasa_split_invoice(self):
        self.ensure_one()
        extra = self.env["account.move"]
        if self.artcasa_split_role or self.state != "draft" or self.move_type != "out_invoice":
            return extra
        orders = self.invoice_line_ids.sale_line_ids.order_id
        project = self.artcasa_project_id or orders.mapped("project_id")[:1]
        if not project or not project.artcasa_split_invoicing:
            return extra
        if abs(project.customer_share_percent - 100.0) < 0.01:
            return extra
        project_partner = project.bill_partner_id or project.partner_id
        if not project_partner:
            return extra
        product_lines = self.invoice_line_ids.filtered(lambda l: l.display_type == "product")
        orig_prices = [(line, line.price_unit) for line in product_lines]
        if not orig_prices:
            return extra
        cust_pct = project.customer_share_percent / 100.0
        proj_pct = project.project_share_percent / 100.0
        project_move = self.with_context(artcasa_skip_split=True).copy({
            "partner_id": project_partner.id,
            "artcasa_split_role": "project",
            "artcasa_split_source_id": self.id,
            "artcasa_project_id": project.id,
            "ref": _("حصة المشروع %s%%") % project.project_share_percent,
        })
        project_move.invoice_line_ids.filtered(lambda l: l.display_type == "product").write({
            "sale_line_ids": [Command.clear()],
        })
        copy_lines = project_move.invoice_line_ids.filtered(lambda l: l.display_type == "product")
        for line, price in orig_prices:
            line.with_context(check_move_validity=False).write({"price_unit": price * cust_pct})
        for copy_line, (_line, price) in zip(copy_lines, orig_prices):
            copy_line.with_context(check_move_validity=False).write({"price_unit": price * proj_pct})
        self.with_context(artcasa_skip_split=True).write({
            "artcasa_split_role": "customer",
            "artcasa_project_id": project.id,
            "ref": _("حصة العميل %s%%") % project.customer_share_percent,
        })
        self.message_post(body=_("تم إنشاء فاتورة حصة المشروع %s") % (project_move.name or project_move.id))
        return project_move

    def write(self, vals):
        res = super().write(vals)
        if vals.get("artcasa_project_id") and not self.env.context.get("artcasa_skip_split"):
            for move in self:
                move._artcasa_split_invoice()
        return res
