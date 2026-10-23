import logging
from html import escape

from odoo import api, models
from odoo.tools.misc import formatLang

_logger = logging.getLogger(__name__)

ALERT_EMAIL = "info@homeblendstore.com"


def notify_sales_event(records, action, document_kind):
    """Send one email per record. A mail failure must not block the sale."""
    if not records or records.env.context.get("install_mode") or records.env.context.get("hb_skip_sales_alert"):
        return
    email_to = records.env["ir.config_parameter"].sudo().get_param("homeblend.sales_alert_email", ALERT_EMAIL)
    if not email_to:
        return
    base_url = records.env["ir.config_parameter"].sudo().get_param("web.base.url", "").rstrip("/")
    for record in records:
        try:
            record._hb_send_sales_alert(action, document_kind, email_to, base_url)
        except Exception:
            _logger.exception("Sales alert email failed for %s %s", record._name, record.id)


class SalesAlertMixin(models.AbstractModel):
    _name = "homeblend.sales.alert.mixin"
    _description = "إشعار إجراءات المبيعات"

    def _hb_alert_number(self):
        self.ensure_one()
        name = self.display_name or self.name or ""
        if not name or name == "/":
            return "مسودة"
        return name

    def _hb_alert_partner(self):
        self.ensure_one()
        partner = getattr(self, "partner_id", False)
        return partner.display_name if partner else ""

    def _hb_alert_amount(self):
        self.ensure_one()
        amount = self.amount_total if "amount_total" in self._fields else getattr(self, "amount", 0.0)
        currency = self.currency_id if "currency_id" in self._fields else self.company_id.currency_id
        return formatLang(self.env, amount or 0.0, currency_obj=currency)

    def _hb_send_sales_alert(self, action, document_kind, email_to, base_url):
        self.ensure_one()
        number = self._hb_alert_number()
        company = self.company_id.name or ""
        partner = self._hb_alert_partner()
        amount = self._hb_alert_amount()
        user = self.env.user.display_name or ""
        link = f"{base_url}/web#id={self.id}&model={self._name}&view_type=form" if base_url else ""
        subject = f"{action} — {number} — {company}"
        rows = [
            ("الإجراء", action),
            ("المستند", document_kind),
            ("الرقم", number),
            ("العميل", partner),
            ("المبلغ", amount),
            ("الشركة", company),
            ("بواسطة", user),
        ]
        body_rows = "".join(
            f"<tr><td style='padding:6px 10px;color:#6d6258'>{escape(label)}</td>"
            f"<td style='padding:6px 10px'>{escape(value or '-')}</td></tr>"
            for label, value in rows
        )
        link_html = (
            f"<p><a href='{escape(link)}'>فتح المستند في أودو</a></p>" if link else ""
        )
        body = f"""
<div dir="rtl" style="font-family:sans-serif;color:#1c1612">
  <p>تم تنفيذ إجراء في المبيعات.</p>
  <table style="border-collapse:collapse">{body_rows}</table>
  {link_html}
</div>
"""
        mail = self.env["mail.mail"].sudo().create({
            "subject": subject,
            "email_from": ALERT_EMAIL,
            "email_to": email_to,
            "body_html": body,
            "auto_delete": False,
        })
        mail.send(raise_exception=False)


class SaleOrder(models.Model):
    _name = "sale.order"
    _inherit = ["sale.order", "homeblend.sales.alert.mixin"]

    @api.model_create_multi
    def create(self, vals_list):
        orders = super().create(vals_list)
        notify_sales_event(
            orders.filtered(lambda order: order.state in ("draft", "sent")),
            "إنشاء عرض سعر",
            "أمر بيع بحالة مسودة",
        )
        return orders

    def action_confirm(self):
        result = super().action_confirm()
        notify_sales_event(self, "تأكيد أمر البيع", "أمر بيع مؤكد")
        return result


class AccountMove(models.Model):
    _name = "account.move"
    _inherit = ["account.move", "homeblend.sales.alert.mixin"]

    @api.model_create_multi
    def create(self, vals_list):
        moves = super().create(vals_list)
        notify_sales_event(
            moves.filtered(lambda move: move._hb_is_sales_invoice_alert()),
            "إنشاء فاتورة",
            "فاتورة عميل مسودة",
        )
        return moves

    def _post(self, soft=True):
        drafts = self.filtered(lambda move: move.state == "draft" and move._hb_is_sales_invoice_alert())
        posted = super()._post(soft=soft)
        notify_sales_event(
            drafts.filtered(lambda move: move.state == "posted"),
            "ترحيل الفاتورة",
            "فاتورة مرحّلة",
        )
        return posted

    def _hb_is_sales_invoice_alert(self):
        self.ensure_one()
        if self.move_type != "out_invoice":
            return False
        if getattr(self, "is_commission_invoice", False) or getattr(self, "is_late_fee_invoice", False):
            return False
        return True


class AccountPayment(models.Model):
    _name = "account.payment"
    _inherit = ["account.payment", "homeblend.sales.alert.mixin"]

    def _hb_alert_amount(self):
        self.ensure_one()
        return formatLang(self.env, self.amount or 0.0, currency_obj=self.currency_id)

    def action_post(self):
        to_notify = self.filtered(
            lambda payment: payment.state in (False, "draft")
            and payment.payment_type == "inbound"
            and payment.partner_type == "customer"
        )
        result = super().action_post()
        notify_sales_event(to_notify.exists(), "تسجيل دفعة", "إيصال تحصيل")
        return result
