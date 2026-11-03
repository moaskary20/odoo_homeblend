import base64
import re

from odoo import api, fields, models, _
from odoo.exceptions import UserError


def _ean13_check_digit(twelve):
    total = sum(int(digit) * (3 if index % 2 else 1) for index, digit in enumerate(twelve))
    return str((10 - total % 10) % 10)


class ProductTemplate(models.Model):
    _inherit = "product.template"

    hb_barcode_image = fields.Binary(
        string="صورة الباركود",
        attachment=True,
        copy=False,
    )
    hb_barcode_image_filename = fields.Char(string="اسم ملف الباركود", copy=False)

    def _hb_barcode_value(self):
        self.ensure_one()
        return (self.barcode or self.default_code or "").strip()

    def _hb_next_ean13(self, used):
        counter = max((int(code[6:12]) for code in used if len(code) == 13 and code.startswith("622100")), default=5)
        while True:
            counter += 1
            base = "622100%06d" % counter
            candidate = base + _ean13_check_digit(base)
            if candidate not in used:
                used.add(candidate)
                return candidate

    def _hb_ensure_barcode(self):
        """تعيين باركود EAN-13 للمنتجات التي بلا رقم."""
        Product = self.env["product.product"].sudo()
        used = set(Product.search([("barcode", "like", "622100%")]).mapped("barcode"))
        used.update(Product.search([("barcode", "!=", False)]).mapped("barcode"))
        for tmpl in self:
            if tmpl.barcode:
                continue
            # استخدم الكود الداخلي إن وُجد وكان فريداً وقابلاً للمسح
            code = (tmpl.default_code or "").strip()
            if code and code not in used and re.fullmatch(r"[A-Za-z0-9\-_./]+", code):
                tmpl.sudo().write({"barcode": code})
                used.add(code)
                continue
            tmpl.sudo().write({"barcode": self._hb_next_ean13(used)})

    def _hb_render_barcode_png(self, value):
        self.ensure_one()
        barcode_type = "EAN13" if len(value) == 13 and value.isdigit() else "Code128"
        try:
            png = self.env["ir.actions.report"].barcode(
                barcode_type,
                value,
                width=700,
                height=140,
                humanreadable=1,
                quiet=0,
            )
        except Exception:
            png = self.env["ir.actions.report"].barcode(
                "Code128",
                value,
                width=700,
                height=140,
                humanreadable=1,
                quiet=0,
            )
        return base64.b64encode(png)

    def action_hb_generate_barcode_image(self):
        """توليد رقم وصورة الباركود للمنتجات المحددة."""
        self._hb_ensure_barcode()
        # أعد القراءة بعد تعيين الباركود على المتغيرات
        self.invalidate_recordset(["barcode"])
        for tmpl in self:
            value = tmpl._hb_barcode_value()
            if not value:
                continue
            tmpl.write({
                "hb_barcode_image": tmpl._hb_render_barcode_png(value),
                "hb_barcode_image_filename": "barcode_%s.png" % value,
            })
        return True

    def action_hb_print_barcode(self):
        self.ensure_one()
        if not self.hb_barcode_image:
            self.action_hb_generate_barcode_image()
        if not self.hb_barcode_image:
            raise UserError(_("لا يوجد باركود لهذا المنتج."))
        return self.env.ref("homeblend_tenant.action_report_hb_product_barcode").report_action(self)

    @api.model
    def hb_generate_all_barcode_images(self, only_missing=True, limit=0):
        """توليد جماعي يُستدعى من المعالج أو سطر الأوامر."""
        domain = [("active", "=", True)]
        products = self.search(domain, order="id")
        if only_missing:
            products = products.filtered(lambda p: not p.hb_barcode_image or not p.barcode)
        if limit:
            products = products[:limit]
        # دفعات لتجنب ضغط الذاكرة
        batch_size = 100
        done = 0
        for index in range(0, len(products), batch_size):
            products[index:index + batch_size].action_hb_generate_barcode_image()
            done += len(products[index:index + batch_size])
            self.env.cr.commit()
        return done


class HomeblendProductBarcodeWizard(models.TransientModel):
    _name = "homeblend.product.barcode.wizard"
    _description = "توليد باركودات المنتجات"

    only_missing = fields.Boolean(
        string="المنتجات الناقصة فقط",
        default=True,
        help="إنشاء الباركود والصورة للمنتجات بلا رقم أو بلا صورة.",
    )
    result_message = fields.Char(string="النتيجة", readonly=True)

    def action_generate(self):
        self.ensure_one()
        done = self.env["product.template"].hb_generate_all_barcode_images(
            only_missing=self.only_missing,
        )
        self.result_message = _("تم تجهيز باركود وصورة لـ %s منتج.") % done
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }
