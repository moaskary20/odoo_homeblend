from urllib.parse import quote

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.fields import Command


class ArtcasaProductLabelWizard(models.TransientModel):
    _name = "artcasa.product.label.wizard"
    _description = "طباعة ملصقات منتجات Art Casa"

    line_ids = fields.One2many("artcasa.product.label.line", "wizard_id", string="الملصقات")
    copies = fields.Integer(string="عدد النسخ لكل سطر", default=1)
    include_price = fields.Boolean(string="إظهار سعر البيع على الملصق")
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        model = self.env.context.get("active_model")
        ids = self.env.context.get("active_ids") or []
        if self.env.context.get("active_id") and not ids:
            ids = [self.env.context["active_id"]]
        lines = []
        if model == "product.template":
            for tmpl in self.env["product.template"].browse(ids):
                for variant in tmpl.product_variant_ids:
                    lines.append(Command.create({"product_id": variant.id, "copies": 1}))
        elif model == "product.product":
            for product in self.env["product.product"].browse(ids):
                lines.append(Command.create({"product_id": product.id, "copies": 1}))
        elif model == "stock.lot":
            for lot in self.env["stock.lot"].browse(ids):
                lines.append(Command.create({
                    "product_id": lot.product_id.id,
                    "lot_id": lot.id,
                    "copies": 1,
                }))
        if lines:
            res["line_ids"] = lines
        return res

    def action_apply_copies(self):
        self.ensure_one()
        copies = max(1, self.copies or 1)
        self.line_ids.write({"copies": copies})
        return True

    def action_print(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_("أضف صنفاً واحداً على الأقل قبل الطباعة."))
        self.line_ids._ensure_barcode()
        return self.env.ref("artcasa_operations.action_report_artcasa_product_label").report_action(self)

    def _iter_labels(self):
        self.ensure_one()
        labels = []
        for line in self.line_ids:
            payload = line._label_payload()
            for _copy in range(max(1, line.copies or 1)):
                labels.append(payload)
        return labels


class ArtcasaProductLabelLine(models.TransientModel):
    _name = "artcasa.product.label.line"
    _description = "سطر ملصق منتج Art Casa"

    wizard_id = fields.Many2one("artcasa.product.label.wizard", required=True, ondelete="cascade")
    product_id = fields.Many2one("product.product", string="المنتج", required=True)
    lot_id = fields.Many2one("stock.lot", string="التشغيلة / التسلسل")
    copies = fields.Integer(string="عدد الملصقات", required=True, default=1)
    barcode = fields.Char(string="الباركود", compute="_compute_barcode")

    @api.depends("product_id.barcode", "product_id.default_code", "lot_id.name")
    def _compute_barcode(self):
        for line in self:
            line.barcode = line._code()

    def _code(self):
        self.ensure_one()
        if self.lot_id:
            return (self.lot_id.name or "").strip()
        product = self.product_id
        return ((product.barcode or product.default_code or "") if product else "").strip()

    def _ensure_barcode(self):
        for line in self:
            if line.lot_id or not line.product_id:
                continue
            if line.product_id.barcode or line.product_id.default_code:
                continue
            line.product_id.sudo().write({"barcode": "AC%06d" % line.product_id.id})

    def _label_payload(self):
        self.ensure_one()
        product = self.product_id
        tmpl = product.product_tmpl_id
        code = self._code() or ("AC%06d" % product.id)
        company = self.wizard_id.company_id or product.company_id or self.env.company
        return {
            "name": product.display_name,
            "brand": tmpl.brand_name or "",
            "code": code,
            "lot": self.lot_id.name if self.lot_id else "",
            "price": product.lst_price if self.wizard_id.include_price else False,
            "currency": company.currency_id,
            "company": company.display_name,
            "barcode_src": self._barcode_src(code, "Code128", 420, 70),
            "qr_src": self._barcode_src(code, "QR", 140, 140),
        }

    def _barcode_src(self, value, barcode_type, width, height):
        return "/report/barcode/?barcode_type=%s&value=%s&width=%s&height=%s&quiet=0" % (
            barcode_type,
            quote(value or "AC", safe=""),
            width,
            height,
        )


class ProductTemplate(models.Model):
    _inherit = "product.template"

    def action_print_artcasa_label(self):
        return {
            "type": "ir.actions.act_window",
            "name": _("طباعة ملصق المنتج"),
            "res_model": "artcasa.product.label.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "active_model": "product.template",
                "active_ids": self.ids,
                "default_company_id": self.env.company.id,
            },
        }


class ProductProduct(models.Model):
    _inherit = "product.product"

    def action_print_artcasa_label(self):
        return {
            "type": "ir.actions.act_window",
            "name": _("طباعة ملصق المنتج"),
            "res_model": "artcasa.product.label.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "active_model": "product.product",
                "active_ids": self.ids,
                "default_company_id": self.env.company.id,
            },
        }


class StockLot(models.Model):
    _inherit = "stock.lot"

    def action_print_artcasa_label(self):
        return {
            "type": "ir.actions.act_window",
            "name": _("طباعة ملصق التشغيلة"),
            "res_model": "artcasa.product.label.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "active_model": "stock.lot",
                "active_ids": self.ids,
                "default_company_id": self.env.company.id,
            },
        }
