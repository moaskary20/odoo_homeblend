from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.fields import Command


class ArtcasaBarcodeInventory(models.TransientModel):
    _name = "artcasa.barcode.inventory"
    _description = "جرد مخزن بالباركود"
    _inherit = ["barcodes.barcode_events_mixin"]

    location_id = fields.Many2one(
        "stock.location",
        string="موقع الجرد",
        required=True,
        default=lambda self: self.env["stock.warehouse"].search(
            [("company_id", "=", self.env.company.id)], limit=1
        ).lot_stock_id,
    )
    company_id = fields.Many2one(related="location_id.company_id")
    barcode_input = fields.Char(string="باركود / كود الصنف")
    line_ids = fields.One2many("artcasa.barcode.inventory.line", "wizard_id", string="الأصناف المعدودة")
    notes = fields.Char(string="ملاحظة الجرد")

    def on_barcode_scanned(self, barcode):
        self.ensure_one()
        self._add_barcode(barcode)

    def action_scan_input(self):
        self.ensure_one()
        if not self.barcode_input:
            raise UserError(_("أدخل باركوداً أو امسحه."))
        self._add_barcode(self.barcode_input)
        self.barcode_input = False
        return True

    def action_scan(self, barcode=None):
        code = barcode
        for wiz in self:
            use = code or wiz.barcode_input
            if not use:
                raise UserError(_("لا يوجد باركود للمسح."))
            wiz._add_barcode(use)
            if not code:
                wiz.barcode_input = False
        return True

    def _add_barcode(self, barcode):
        self.ensure_one()
        code = (barcode or "").strip()
        product = self.env["product.product"].search(
            ["|", ("barcode", "=", code), ("default_code", "=", code)], limit=1
        )
        lot = self.env["stock.lot"]
        if not product:
            # الأصناف المتتبعة تُعدّ بمسح ملصق التشغيلة/التسلسل لا ملصق الصنف.
            lot = lot.search([
                ("name", "=", code),
                ("company_id", "in", [self.company_id.id, False]),
            ], limit=1)
            product = lot.product_id
        if not product:
            raise UserError(_("لا يوجد منتج أو رقم تشغيلة بالباركود %s") % code)
        if product.tracking != "none" and not lot:
            raise UserError(_(
                "الصنف %s متتبع بالتشغيلات، امسح ملصق رقم التشغيلة/التسلسل بدل ملصق الصنف."
            ) % product.display_name)

        line = self.line_ids.filtered(
            lambda l: l.product_id.id == product.id and l.lot_id.id == lot.id
        )[:1]
        if line:
            if product.tracking == "serial":
                raise UserError(_("الرقم التسلسلي %s ممسوح بالفعل.") % lot.name)
            line.qty_counted += 1.0
            return
        self.update({
            "line_ids": [Command.create({
                "product_id": product.id,
                "lot_id": lot.id,
                "barcode": code,
                "qty_on_hand": self._on_hand(product, lot),
                "qty_counted": 1.0,
            })],
        })

    def _on_hand(self, product, lot):
        self.ensure_one()
        domain = [("product_id", "=", product.id), ("location_id", "=", self.location_id.id)]
        if lot:
            domain.append(("lot_id", "=", lot.id))
        return sum(self.env["stock.quant"].search(domain).mapped("quantity"))

    def action_apply(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_("امسح صنفاً واحداً على الأقل قبل اعتماد الجرد."))
        Quant = self.env["stock.quant"].with_context(inventory_mode=True)
        quants = Quant.browse()
        for line in self.line_ids:
            domain = [
                ("product_id", "=", line.product_id.id),
                ("location_id", "=", self.location_id.id),
            ]
            if line.lot_id:
                domain.append(("lot_id", "=", line.lot_id.id))
            quant = Quant.search(domain, limit=1)
            if not quant:
                quant = Quant.create({
                    "product_id": line.product_id.id,
                    "location_id": self.location_id.id,
                    "lot_id": line.lot_id.id or False,
                })
            quant.inventory_quantity = line.qty_counted
            quants |= quant
        result = quants.action_apply_inventory()
        if isinstance(result, dict):
            return result
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("تم الجرد"),
                "message": _("اعتمد الجرد لـ %s صنفاً في %s") % (len(self.line_ids), self.location_id.display_name),
                "type": "success",
                "next": {"type": "ir.actions.act_window_close"},
            },
        }


class ArtcasaBarcodeInventoryLine(models.TransientModel):
    _name = "artcasa.barcode.inventory.line"
    _description = "سطر جرد باركود"

    wizard_id = fields.Many2one("artcasa.barcode.inventory", required=True, ondelete="cascade")
    product_id = fields.Many2one("product.product", string="المنتج", required=True)
    lot_id = fields.Many2one("stock.lot", string="التشغيلة / التسلسل")
    barcode = fields.Char(string="الباركود الممسوح")
    qty_on_hand = fields.Float(string="الكمية الدفترية")
    qty_counted = fields.Float(string="الكمية المعدودة", required=True, default=1.0)
    difference = fields.Float(string="الفرق", compute="_compute_difference")

    @api.depends("qty_on_hand", "qty_counted")
    def _compute_difference(self):
        for line in self:
            line.difference = line.qty_counted - line.qty_on_hand
