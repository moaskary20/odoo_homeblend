import logging
from collections import defaultdict
from html import escape

from odoo import fields, models
from odoo.tools.misc import formatLang

_logger = logging.getLogger(__name__)

ALERT_EMAIL = "info@homeblendstore.com"


class PosSession(models.Model):
    _inherit = "pos.session"

    def _validate_session(self, balancing_account=False, amount_to_balance=0, bank_payment_method_diffs=None):
        result = super()._validate_session(
            balancing_account=balancing_account,
            amount_to_balance=amount_to_balance,
            bank_payment_method_diffs=bank_payment_method_diffs,
        )
        if result is True:
            for session in self.filtered(lambda item: item.state == "closed"):
                session._hb_email_closing_report()
        return result

    def _hb_money(self, amount):
        self.ensure_one()
        return formatLang(self.env, amount or 0.0, currency_obj=self.currency_id)

    def _hb_when(self, value):
        if not value:
            return "-"
        local = fields.Datetime.context_timestamp(self, value)
        return local.strftime("%Y-%m-%d %H:%M")

    def _hb_email_closing_report(self):
        self.ensure_one()
        if self.env.context.get("install_mode") or self.env.context.get("hb_skip_sales_alert"):
            return
        email_to = self.env["ir.config_parameter"].sudo().get_param("homeblend.sales_alert_email", ALERT_EMAIL)
        if not email_to:
            return
        try:
            mail = self.env["mail.mail"].sudo().create({
                "subject": "إغلاق خزينة — %s — %s" % (self.config_id.name or "", self.name or ""),
                "email_from": ALERT_EMAIL,
                "email_to": email_to,
                "body_html": self._hb_closing_report_html(),
                "auto_delete": False,
            })
            mail.send(raise_exception=False)
        except Exception:
            _logger.exception("POS closing report email failed for session %s", self.id)

    def _hb_closing_report_html(self):
        self.ensure_one()
        orders = self.order_ids.filtered(lambda order: order.state not in ("draft", "cancel")).sorted("date_order")
        sales = orders.filtered(lambda order: not order.is_refund)
        refunds = orders.filtered("is_refund")
        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url", "").rstrip("/")
        link = "%s/web#id=%s&model=pos.session&view_type=form" % (base_url, self.id) if base_url else ""

        summary = [
            ("الشركة", self.company_id.name),
            ("نقطة البيع", self.config_id.name),
            ("الجلسة", self.name),
            ("فُتحت بواسطة", self.user_id.name),
            ("أُغلقت بواسطة", self.env.user.name),
            ("وقت الفتح", self._hb_when(self.start_at)),
            ("وقت الإغلاق", self._hb_when(self.stop_at)),
            ("عدد الطلبات", str(len(sales))),
            ("عدد المرتجعات", str(len(refunds))),
            ("مبيعات", self._hb_money(sum(sales.mapped("amount_total")))),
            ("مرتجعات", self._hb_money(sum(refunds.mapped("amount_total")))),
            ("صافي الجلسة", self._hb_money(sum(orders.mapped("amount_total")))),
            ("إجمالي المدفوعات", self._hb_money(self.total_payments_amount)),
        ]
        if self.config_id.cash_control:
            summary.extend([
                ("رصيد الافتتاح", self._hb_money(self.cash_register_balance_start)),
                ("النقد المتوقع", self._hb_money(self.cash_register_balance_end)),
                ("النقد المعدود", self._hb_money(self.cash_register_balance_end_real)),
                ("فرق الخزينة", self._hb_money(self.cash_register_difference)),
            ])

        return """
<div dir="rtl" style="font-family:sans-serif;color:#1c1612">
  <h2 style="margin:0 0 12px">تقرير إغلاق خزينة نقطة البيع</h2>
  %s
  <h3>المدفوعات حسب الوسيلة</h3>
  %s
  <h3>الأصناف</h3>
  %s
  <h3>تفصيل المعاملات</h3>
  %s
  %s
</div>
""" % (
            self._hb_html_table(("البند", "القيمة"), summary),
            self._hb_payments_table(orders),
            self._hb_products_table(orders),
            self._hb_orders_html(orders),
            ("<p><a href='%s'>فتح الجلسة في أودو</a></p>" % escape(link)) if link else "",
        )

    def _hb_html_table(self, header, rows):
        head = "".join(
            "<th style='padding:6px 8px;background:#f6f0e6;text-align:right'>%s</th>" % escape(title)
            for title in header
        )
        body = []
        for row in rows:
            cells = "".join(
                "<td style='padding:6px 8px;border-top:1px solid #e6d9c6'>%s</td>" % escape(str(cell or "-"))
                for cell in row
            )
            body.append("<tr>%s</tr>" % cells)
        if not body:
            body.append("<tr><td colspan='%s' style='padding:6px 8px'>لا يوجد</td></tr>" % len(header))
        return "<table style='border-collapse:collapse;width:100%%;margin:0 0 16px'><tr>%s</tr>%s</table>" % (
            head,
            "".join(body),
        )

    def _hb_payments_table(self, orders):
        grouped = defaultdict(lambda: {"count": 0, "amount": 0.0})
        for payment in orders.payment_ids:
            name = payment.payment_method_id.name or "غير محدد"
            grouped[name]["count"] += 1
            grouped[name]["amount"] += payment.amount
        rows = [
            (name, str(values["count"]), self._hb_money(values["amount"]))
            for name, values in sorted(grouped.items())
        ]
        return self._hb_html_table(("الوسيلة", "عدد العمليات", "المبلغ"), rows)

    def _hb_products_table(self, orders):
        grouped = defaultdict(lambda: {"qty": 0.0, "amount": 0.0})
        for line in orders.lines:
            name = line.full_product_name or line.product_id.display_name or "صنف"
            grouped[name]["qty"] += line.qty
            grouped[name]["amount"] += line.price_subtotal_incl
        rows = [
            (name, "%g" % values["qty"], self._hb_money(values["amount"]))
            for name, values in sorted(grouped.items())
        ]
        return self._hb_html_table(("الصنف", "الكمية", "الإجمالي شامل الضريبة"), rows)

    def _hb_orders_html(self, orders):
        blocks = []
        for order in orders:
            kind = "مرتجع" if order.is_refund else "بيع"
            invoice = order.account_move.name if order.account_move and order.account_move.name != "/" else "-"
            payments = "، ".join(
                "%s %s" % (payment.payment_method_id.name or "", self._hb_money(payment.amount))
                for payment in order.payment_ids
            ) or "-"
            blocks.append("<h4 style='margin:16px 0 6px'>%s — %s — %s</h4>" % (
                escape(kind),
                escape(order.pos_reference or order.name or ""),
                escape(self._hb_money(order.amount_total)),
            ))
            blocks.append(self._hb_html_table(
                ("البند", "القيمة"),
                [
                    ("الوقت", self._hb_when(order.date_order)),
                    ("العميل", order.partner_id.name or "بدون عميل"),
                    ("الفاتورة", invoice),
                    ("المدفوعات", payments),
                ],
            ))
            line_rows = [
                (
                    line.full_product_name or line.product_id.display_name,
                    "%g" % line.qty,
                    self._hb_money(line.price_unit),
                    self._hb_money(line.price_subtotal_incl),
                )
                for line in order.lines
            ]
            blocks.append(self._hb_html_table(("الصنف", "الكمية", "السعر", "الإجمالي"), line_rows))
        return "".join(blocks) or "<p>لا توجد معاملات في هذه الجلسة.</p>"
