from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command


class AccountMove(models.Model):
    _inherit = "account.move"

    tenant_id = fields.Many2one(
        "res.partner",
        string="المستأجر",
        domain="[('is_tenant', '=', True)]",
        index=True,
        tracking=True,
    )
    homeblend_contract_id = fields.Many2one("homeblend.tenant.contract", string="عقد العمولة")
    is_commission_invoice = fields.Boolean(string="فاتورة عمولة Home Blend", copy=False)
    source_sale_invoice_id = fields.Many2one("account.move", string="فاتورة البيع المصدر", copy=False)
    commission_amount = fields.Monetary(string="قيمة العمولة", copy=False)
    commission_invoice_id = fields.Many2one("account.move", string="فاتورة العمولة", copy=False)
    is_late_fee_invoice = fields.Boolean(string="فاتورة غرامة تأخير", copy=False)
    late_fee_invoice_id = fields.Many2one("account.move", string="فاتورة الغرامة", copy=False)
    homeblend_qr_payload = fields.Char(string="QR الفاتورة", compute="_compute_homeblend_qr_payload")
    paper_invoice = fields.Binary(string="الفاتورة الورقية", attachment=True, copy=False)
    paper_invoice_filename = fields.Char(string="اسم ملف الفاتورة الورقية", copy=False)
    has_paper_invoice = fields.Boolean(
        string="يوجد فاتورة ورقية",
        compute="_compute_has_paper_invoice",
        store=True,
    )

    @api.depends("paper_invoice")
    def _compute_has_paper_invoice(self):
        for move in self:
            move.has_paper_invoice = bool(move.paper_invoice)

    def _post(self, soft=True):
        posted = super()._post(soft=soft)
        posted._homeblend_generate_commission()
        return posted

    def _compute_homeblend_qr_payload(self):
        for move in self:
            eta = getattr(move, "l10n_eg_qr_code", False)
            if eta:
                move.homeblend_qr_payload = eta
                continue
            if move.move_type not in ("out_invoice", "out_refund") or move.state != "posted":
                move.homeblend_qr_payload = False
                continue
            move.homeblend_qr_payload = "|".join([
                move.company_id.name or "",
                move.company_id.vat or move.company_id.partner_id.vat or "",
                move.name or "",
                str(move.invoice_date or ""),
                "%.2f" % (move.amount_total or 0.0),
                "%.2f" % (move.amount_tax or 0.0),
                move.partner_id.vat or "",
            ])

    def _homeblend_generate_commission(self):
        for move in self:
            if (
                move.move_type != "out_invoice"
                or move.is_commission_invoice
                or move.commission_invoice_id
                or not move.tenant_id
            ):
                continue
            contract = move.homeblend_contract_id or self.env["homeblend.tenant.contract"].get_active_for_tenant(
                move.tenant_id, move.company_id
            )
            if not contract:
                continue
            base = move.amount_untaxed if contract.commission_base == "before_tax" else move.amount_total
            commission = move.currency_id.round(base * (contract.commission_percent / 100.0))
            if commission <= 0:
                continue
            product_tmpl = self.env.ref("homeblend_tenant.product_commission_fee", raise_if_not_found=False)
            if not product_tmpl:
                raise UserError(_("منتج العمولة غير موجود. أعد تثبيت موديول المستأجرين."))
            product = product_tmpl.product_variant_id
            taxes = product.taxes_id.filtered(
                lambda t: t.company_id == move.company_id
                and (not t.country_id or t.country_id == move.company_id.account_fiscal_country_id)
            )
            invoice = self.env["account.move"].sudo().create({
                "move_type": "out_invoice",
                "partner_id": move.tenant_id.id,
                "company_id": move.company_id.id,
                "invoice_origin": move.name,
                "invoice_date": fields.Date.context_today(move),
                "is_commission_invoice": True,
                "source_sale_invoice_id": move.id,
                "homeblend_contract_id": contract.id,
                "tenant_id": move.tenant_id.id,
                "commission_amount": commission,
                "invoice_line_ids": [Command.create({
                    "product_id": product.id,
                    "name": _("عمولة Home Blend %s%% على %s") % (contract.commission_percent, move.name),
                    "quantity": 1,
                    "price_unit": commission,
                    "tax_ids": [Command.set(taxes.ids)],
                })],
            })
            try:
                invoice.action_post()
            except (UserError, ValidationError):
                invoice.message_post(body=_("فاتورة العمولة جاهزة للمراجعة قبل الاعتماد."))
            move.commission_invoice_id = invoice.id
            move.message_post(body=_("تم إنشاء فاتورة عمولة %s بقيمة %s") % (invoice.name or invoice.id, commission))

    def _homeblend_late_fee_product(self):
        tmpl = self.env.ref("homeblend_tenant.product_late_fee", raise_if_not_found=False)
        if tmpl:
            return tmpl.product_variant_id
        return self.env["product.product"].search([("default_code", "=", "HB-LATE-FEE")], limit=1)

    @api.model
    def _cron_homeblend_late_fees(self):
        today = fields.Date.context_today(self)
        invoices = self.search([
            ("move_type", "=", "out_invoice"),
            ("state", "=", "posted"),
            ("payment_state", "in", ["not_paid", "partial"]),
            ("invoice_date_due", "<", today),
            ("is_commission_invoice", "=", False),
            ("is_late_fee_invoice", "=", False),
            ("late_fee_invoice_id", "=", False),
            ("tenant_id", "!=", False),
        ])
        product = self._homeblend_late_fee_product()
        for move in invoices:
            contract = move.homeblend_contract_id or self.env["homeblend.tenant.contract"].get_active_for_tenant(
                move.tenant_id, move.company_id
            )
            if not contract or not contract.late_fee_percent:
                continue
            amount = move.currency_id.round(move.amount_residual * (contract.late_fee_percent / 100.0))
            if amount <= 0:
                continue
            if not product:
                move.message_post(body=_("تعذر إنشاء غرامة التأخير: منتج الغرامة غير موجود."))
                continue
            taxes = product.taxes_id.filtered(
                lambda t: t.company_id == move.company_id
                and (not t.country_id or t.country_id == move.company_id.account_fiscal_country_id)
            )
            fee = self.sudo().create({
                "move_type": "out_invoice",
                "partner_id": move.partner_id.id,
                "company_id": move.company_id.id,
                "invoice_origin": move.name,
                "invoice_date": today,
                "is_late_fee_invoice": True,
                "tenant_id": move.tenant_id.id,
                "homeblend_contract_id": contract.id,
                "invoice_line_ids": [Command.create({
                    "product_id": product.id,
                    "name": _("غرامة تأخير %s%% على %s") % (contract.late_fee_percent, move.name),
                    "quantity": 1,
                    "price_unit": amount,
                    "tax_ids": [Command.set(taxes.ids)],
                })],
            })
            move.late_fee_invoice_id = fee.id
            move.message_post(body=_("تم إنشاء فاتورة غرامة تأخير %s بقيمة %s") % (fee.name or fee.id, amount))
        return True

    def action_generate_late_fees(self):
        return self._cron_homeblend_late_fees()

    def action_open_paper_invoice(self):
        self.ensure_one()
        return True

    def _sync_paper_invoice_document(self):
        if self.env.context.get("skip_paper_doc_sync") or "homeblend.document" not in self.env:
            return True
        Document = self.env["homeblend.document"].sudo().with_context(skip_paper_invoice_push=True)
        for move in self:
            if move.move_type not in ("out_invoice", "out_refund"):
                continue
            domain = [
                ("res_model", "=", "account.move"),
                ("res_id", "=", move.id),
                ("document_type", "=", "invoice"),
            ]
            doc = Document.search(domain, limit=1)
            if "invoice_id" in Document._fields:
                doc = doc or Document.search([("invoice_id", "=", move.id)], limit=1)
            if not move.paper_invoice:
                continue
            vals = {
                "name": move.paper_invoice_filename or _("فاتورة ورقية %s") % (move.name or move.id),
                "datas": move.paper_invoice,
                "datas_fname": move.paper_invoice_filename,
                "document_type": "invoice",
                "partner_id": move.partner_id.id,
                "company_id": move.company_id.id,
                "res_model": "account.move",
                "res_id": move.id,
            }
            if "invoice_id" in Document._fields:
                vals["invoice_id"] = move.id
            if doc:
                doc.write(vals)
            else:
                Document.create(vals)
        return True

    @api.model_create_multi
    def create(self, vals_list):
        moves = super().create(vals_list)
        for move in moves:
            if move.move_type == "out_invoice" and not move.tenant_id and move.invoice_origin:
                so = self.env["sale.order"].search([("name", "=", move.invoice_origin)], limit=1)
                if so and so.tenant_id:
                    move.tenant_id = so.tenant_id
                    move.homeblend_contract_id = so.tenant_contract_id
        moves.filtered("paper_invoice")._sync_paper_invoice_document()
        return moves

    def write(self, vals):
        res = super().write(vals)
        if "paper_invoice" in vals or "paper_invoice_filename" in vals:
            self._sync_paper_invoice_document()
        return res
