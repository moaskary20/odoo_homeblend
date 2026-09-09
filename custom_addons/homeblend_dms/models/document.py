from odoo import api, fields, models, _


class HomeblendDocument(models.Model):
    _name = "homeblend.document"
    _description = "وثيقة"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(string="الاسم", required=True, tracking=True)
    reference = fields.Char(string="المرجع", copy=False, default=lambda self: _("New"))
    datas = fields.Binary(string="الملف", required=True, attachment=True)
    datas_fname = fields.Char(string="اسم الملف")
    partner_id = fields.Many2one("res.partner", string="الشريك", tracking=True)
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company, index=True)
    res_model = fields.Char(string="النموذج المرتبط")
    res_id = fields.Integer(string="معرف السجل")
    document_type = fields.Selection(
        [
            ("contract", "عقد"),
            ("invoice", "فاتورة"),
            ("guarantee", "ضمان"),
            ("hr", "موارد بشرية"),
            ("other", "أخرى"),
        ],
        default="other",
        required=True,
        tracking=True,
    )
    sign_state = fields.Selection(
        [
            ("draft", "مسودة"),
            ("pending", "بانتظار التوقيع"),
            ("signed", "موقع"),
            ("refused", "مرفوض"),
        ],
        default="draft",
        tracking=True,
        copy=False,
    )
    signed_by = fields.Many2one("res.users", string="وقّع بواسطة", copy=False)
    signed_date = fields.Datetime(string="تاريخ التوقيع", copy=False)
    signature = fields.Binary(string="التوقيع", attachment=True, copy=False)
    notes = fields.Text(string="ملاحظات")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("reference", _("New")) == _("New"):
                vals["reference"] = self.env["ir.sequence"].next_by_code("homeblend.document") or _("New")
            if not vals.get("name") and vals.get("datas_fname"):
                vals["name"] = vals["datas_fname"]
        return super().create(vals_list)

    def action_request_sign(self):
        self.write({"sign_state": "pending"})
        for rec in self:
            rec.activity_schedule(
                "mail.mail_activity_data_todo",
                summary=_("توقيع الوثيقة %s") % rec.name,
                user_id=self.env["res.users"].search([("partner_id", "=", rec.partner_id.id)], limit=1).id or self.env.user.id,
            )
        return True

    def action_sign(self):
        self.write({
            "sign_state": "signed",
            "signed_by": self.env.user.id,
            "signed_date": fields.Datetime.now(),
        })
        return True

    def action_refuse(self):
        self.write({"sign_state": "refused"})
        return True
