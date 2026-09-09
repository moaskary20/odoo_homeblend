from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class ProjectProject(models.Model):
    _inherit = "project.project"

    artcasa_split_invoicing = fields.Boolean(string="تقسيم الفاتورة مشروع / عميل")
    customer_share_percent = fields.Float(string="نسبة العميل %", default=50.0)
    project_share_percent = fields.Float(string="نسبة المشروع %", default=50.0)
    bill_partner_id = fields.Many2one("res.partner", string="شريك فاتورة المشروع")
    currency_id = fields.Many2one(related="company_id.currency_id")
    contract_date_start = fields.Date(string="بداية عقد المشروع")
    contract_date_end = fields.Date(string="نهاية عقد المشروع")
    contract_value = fields.Monetary(string="قيمة العقد", currency_field="currency_id")
    contract_duration_days = fields.Integer(string="مدة العقد (يوم)", compute="_compute_contract_duration")
    contract_guarantee = fields.Char(string="ضمان العقد")
    contract_guarantee_amount = fields.Monetary(string="قيمة الضمان", currency_field="currency_id")
    contract_guarantee_end = fields.Date(string="نهاية سريان الضمان")
    contract_notes = fields.Text(string="شروط العقد")
    payment_term_id = fields.Many2one("account.payment.term", string="دفعات العقد")
    signed = fields.Boolean(string="موقع إلكترونياً", copy=False)
    signed_date = fields.Datetime(string="تاريخ التوقيع", copy=False)
    signed_by = fields.Many2one("res.users", string="وقّع بواسطة", copy=False)
    signature = fields.Binary(string="توقيع العقد", attachment=True, copy=False)
    attachment_ids = fields.Many2many("ir.attachment", string="مرفقات العقد")
    contract_progress = fields.Float(string="نسبة الإنجاز %", compute="_compute_contract_finance")
    contract_delayed = fields.Boolean(string="مشروع متأخر", compute="_compute_contract_delayed", store=True)
    collected_amount = fields.Monetary(string="التحصيل", compute="_compute_contract_finance", currency_field="currency_id")
    outstanding_amount = fields.Monetary(string="المستحق", compute="_compute_contract_finance", currency_field="currency_id")
    extract_count = fields.Integer(string="المستخلصات", compute="_compute_contract_finance")

    @api.depends("contract_date_start", "contract_date_end")
    def _compute_contract_duration(self):
        for project in self:
            start, end = project.contract_date_start, project.contract_date_end
            project.contract_duration_days = (end - start).days if start and end else 0

    @api.depends("contract_date_end", "task_ids.is_closed")
    def _compute_contract_delayed(self):
        today = fields.Date.context_today(self)
        for project in self:
            open_tasks = project.task_ids.filtered(lambda t: not t.is_closed)
            project.contract_delayed = bool(
                project.contract_date_end and project.contract_date_end < today and (open_tasks or not project.task_ids)
            )

    def _compute_contract_finance(self):
        Move = self.env["account.move"]
        for project in self:
            total = len(project.task_ids)
            closed = len(project.task_ids.filtered(lambda t: t.is_closed))
            project.contract_progress = (closed / total * 100.0) if total else 0.0
            invoices = Move.search([
                ("artcasa_project_id", "=", project.id),
                ("move_type", "=", "out_invoice"),
                ("state", "=", "posted"),
            ])
            project.collected_amount = sum(inv.amount_total - inv.amount_residual for inv in invoices)
            project.outstanding_amount = sum(invoices.mapped("amount_residual"))
            project.extract_count = len(invoices)

    def action_sign_contract(self):
        for project in self:
            if not project.signature:
                raise UserError(_("ارسم التوقيع على العقد قبل الاعتماد."))
            project.write({
                "signed": True,
                "signed_date": fields.Datetime.now(),
                "signed_by": self.env.user.id,
            })
            Document = self.env["homeblend.document"] if "homeblend.document" in self.env else None
            if Document is not None:
                Document.create({
                    "name": _("عقد مشروع %s") % project.display_name,
                    "document_type": "contract",
                    "partner_id": project.partner_id.id,
                    "company_id": project.company_id.id,
                    "datas": project.signature,
                    "datas_fname": "contract-signature.png",
                    "res_model": "project.project",
                    "res_id": project.id,
                    "sign_state": "signed",
                    "signed_by": self.env.user.id,
                    "signed_date": fields.Datetime.now(),
                })
        return True

    def action_view_extracts(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "مستخلصات المشروع",
            "res_model": "account.move",
            "view_mode": "list,form",
            "domain": [("artcasa_project_id", "=", self.id), ("move_type", "=", "out_invoice")],
            "context": {"default_artcasa_project_id": self.id, "default_move_type": "out_invoice"},
        }

    def _schedule_contract_alert(self, marker, summary, deadline):
        """تنبيه واحد لكل مشروع لكل نوع، فالتذكير اليومي لا يكرّر الأنشطة."""
        self.ensure_one()
        existing = self.env["mail.activity"].search([
            ("res_model", "=", "project.project"),
            ("res_id", "=", self.id),
            ("summary", "ilike", marker),
        ], limit=1)
        if existing:
            return
        self.activity_schedule(
            "mail.mail_activity_data_todo",
            summary=summary,
            date_deadline=deadline,
        )

    @api.model
    def _cron_contract_expiry(self):
        today = fields.Date.context_today(self)
        soon = today + relativedelta(days=30)
        expiring = self.search([
            ("contract_date_end", ">=", today),
            ("contract_date_end", "<=", soon),
        ])
        for project in expiring:
            project._schedule_contract_alert(
                "عقد المشروع",
                _("عقد المشروع ينتهي قريباً: %s") % project.display_name,
                project.contract_date_end,
            )
        for project in self.search([("contract_delayed", "=", True)]):
            project._schedule_contract_alert(
                "مشروع متأخر",
                _("مشروع متأخر: %s") % project.display_name,
                today,
            )
        guarantees = self.search([
            ("contract_guarantee_end", ">=", today),
            ("contract_guarantee_end", "<=", soon),
        ])
        for project in guarantees:
            project._schedule_contract_alert(
                "ضمان المشروع",
                _("ضمان المشروع ينتهي قريباً: %s") % project.display_name,
                project.contract_guarantee_end,
            )

    @api.onchange("customer_share_percent")
    def _onchange_customer_share(self):
        if self.artcasa_split_invoicing:
            self.project_share_percent = 100.0 - (self.customer_share_percent or 0.0)

    @api.onchange("project_share_percent")
    def _onchange_project_share(self):
        if self.artcasa_split_invoicing:
            self.customer_share_percent = 100.0 - (self.project_share_percent or 0.0)

    @api.constrains("artcasa_split_invoicing", "customer_share_percent", "project_share_percent")
    def _check_split_shares(self):
        for project in self:
            if not project.artcasa_split_invoicing:
                continue
            if project.customer_share_percent < 0 or project.project_share_percent < 0:
                raise ValidationError(_("نسب التقسيم لا يمكن أن تكون سالبة."))
            if abs(project.customer_share_percent + project.project_share_percent - 100.0) > 0.05:
                raise ValidationError(_("مجموع نسبة العميل ونسبة المشروع يجب أن يساوي 100%%."))
