from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tools.float_utils import float_compare, float_is_zero

CHANNEL_SELECTION = [
    ("all", "كل الوسائل"),
    ("cash", "نقدي / صندوق"),
    ("bank", "تحويل بنكي"),
    ("card", "بطاقة"),
    ("wallet", "محفظة إلكترونية"),
    ("other", "أخرى"),
]


def _channel_from_text(text, journal_type=None):
    value = (text or "").strip().lower()
    if journal_type == "cash" or any(token in value for token in ("نقد", "صندوق", "خزن", "cash")):
        return "cash"
    if any(token in value for token in ("بطاقة", "فيزا", "مدى", "visa", "card", "mada")):
        return "card"
    if any(token in value for token in ("محفظة", "wallet", "vodafone", "انستا")):
        return "wallet"
    if journal_type == "bank" or any(token in value for token in ("تحويل", "بنك", "bank", "transfer")):
        return "bank"
    return "other"


class HomeblendPaymentSettleBook(models.Model):
    """سطور كشف خارجي (بنك / بطاقة / نقد معدود) للمطابقة."""

    _name = "homeblend.payment.settle.book"
    _description = "سطر كشف لتسوية المدفوعات"
    _order = "date desc, id desc"

    name = fields.Char(string="البيان", required=True)
    date = fields.Date(string="التاريخ", required=True, index=True, default=fields.Date.context_today)
    amount = fields.Monetary(string="المبلغ", required=True)
    currency_id = fields.Many2one(related="company_id.currency_id")
    direction = fields.Selection(
        [("in", "وارد"), ("out", "صادر")],
        string="الاتجاه",
        required=True,
        default="in",
    )
    channel = fields.Selection(CHANNEL_SELECTION[1:], string="وسيلة الدفع", required=True, default="bank")
    reference = fields.Char(string="المرجع")
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
    )
    journal_id = fields.Many2one(
        "account.journal",
        string="دفتر مرتبط",
        domain="[('type', 'in', ('bank', 'cash')), ('company_id', '=', company_id)]",
    )
    state = fields.Selection(
        [("open", "غير مسوّى"), ("matched", "مسوّى"), ("cancel", "ملغى")],
        default="open",
        required=True,
        index=True,
    )
    matched_payment_id = fields.Many2one("account.payment", string="دفعة مطابقة", readonly=True)
    matched_pos_payment_id = fields.Many2one("pos.payment", string="دفعة POS مطابقة", readonly=True)
    match_note = fields.Char(string="ملاحظة المطابقة", readonly=True)

    def action_reset_match(self):
        self.write({
            "state": "open",
            "matched_payment_id": False,
            "matched_pos_payment_id": False,
            "match_note": False,
        })
        return True


class HomeblendPaymentSettle(models.TransientModel):
    _name = "homeblend.payment.settle"
    _description = "تسوية المدفوعات"

    name = fields.Char(compute="_compute_name")
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self._default_company(),
    )
    currency_id = fields.Many2one(related="company_id.currency_id")
    date_from = fields.Date(required=True, default=lambda self: fields.Date.context_today(self).replace(day=1))
    date_to = fields.Date(required=True, default=fields.Date.context_today)
    channel = fields.Selection(CHANNEL_SELECTION, string="وسيلة الدفع", default="all", required=True)
    journal_id = fields.Many2one(
        "account.journal",
        string="دفتر يومية",
        domain="[('type', 'in', ('bank', 'cash')), ('company_id', '=', company_id)]",
    )
    include_account_payments = fields.Boolean(string="مدفوعات المحاسبة", default=True)
    include_pos_payments = fields.Boolean(string="مدفوعات نقطة البيع", default=True)
    include_matched_books = fields.Boolean(string="إظهار المسوّى سابقاً", default=False)
    system_total = fields.Monetary(string="إجمالي النظام", readonly=True)
    book_total = fields.Monetary(string="إجمالي الكشف", readonly=True)
    difference = fields.Monetary(string="الفرق (نظام − كشف)", readonly=True)
    matched_count = fields.Integer(string="عدد المطابقات", readonly=True)
    unmatched_system_count = fields.Integer(string="غير مسوّى بالنظام", readonly=True)
    unmatched_book_count = fields.Integer(string="غير مسوّى بالكشف", readonly=True)
    system_line_ids = fields.One2many("homeblend.payment.settle.system", "settle_id")
    book_line_ids = fields.One2many("homeblend.payment.settle.line", "settle_id")

    @api.model
    def _default_company(self):
        company = self.env["res.company"].search(
            [("name", "ilike", "home"), ("name", "ilike", "blend")],
            limit=1,
        )
        return company or self.env.company

    @api.depends("date_from", "date_to", "channel")
    def _compute_name(self):
        labels = dict(CHANNEL_SELECTION)
        for settle in self:
            settle.name = "تسوية مدفوعات — %s — من %s إلى %s" % (
                labels.get(settle.channel, ""),
                settle.date_from or "",
                settle.date_to or "",
            )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records.action_load()
        return records

    def write(self, vals):
        res = super().write(vals)
        watched = {
            "date_from", "date_to", "company_id", "channel", "journal_id",
            "include_account_payments", "include_pos_payments", "include_matched_books",
        }
        if watched & set(vals):
            self.action_load()
        return res

    def action_open_book_entries(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "سطور الكشف",
            "res_model": "homeblend.payment.settle.book",
            "view_mode": "list,form",
            "domain": [("company_id", "=", self.company_id.id)],
            "context": {
                "default_company_id": self.company_id.id,
                "default_channel": self.channel if self.channel != "all" else "bank",
                "default_journal_id": self.journal_id.id,
                "search_default_open": 1,
            },
        }

    def action_load(self):
        for settle in self:
            settle._rebuild()
        return True

    def action_auto_match(self):
        for settle in self:
            settle._auto_match()
            settle._rebuild()
        return True

    def action_match_selected(self):
        self.ensure_one()
        systems = self.system_line_ids.filtered("selected")
        books = self.book_line_ids.filtered("selected")
        if len(systems) != 1 or len(books) != 1:
            raise UserError(_("اختر سطراً واحداً من النظام وسطراً واحداً من الكشف للمطابقة اليدوية."))
        system = systems[0]
        book = books[0]
        if system.is_matched or book.is_matched:
            raise UserError(_("أحد السطرين مسوّى مسبقاً."))
        currency = self.currency_id
        if float_compare(abs(system.amount), abs(book.amount), precision_rounding=currency.rounding) != 0:
            raise UserError(_("المبلغان غير متساويين. للمطابقة اليدوية يجب أن يتساوى المبلغ."))
        self._apply_match(system, book, note="مطابقة يدوية")
        self._rebuild()
        return True

    def _channel_ok(self, channel):
        self.ensure_one()
        return self.channel == "all" or channel == self.channel

    def _system_rows(self):
        self.ensure_one()
        rows = []
        date_from = self.date_from
        date_to = self.date_to
        company = self.company_id

        if self.include_account_payments:
            domain = [
                ("company_id", "=", company.id),
                ("state", "in", ["in_process", "paid"]),
                ("date", ">=", date_from),
                ("date", "<=", date_to),
            ]
            if self.journal_id:
                domain.append(("journal_id", "=", self.journal_id.id))
            payments = self.env["account.payment"].sudo().search(domain)
            for payment in payments:
                method_name = payment.payment_method_line_id.name or ""
                channel = _channel_from_text(method_name, payment.journal_id.type)
                if not self._channel_ok(channel):
                    continue
                amount = payment.amount
                if payment.payment_type == "outbound":
                    signed = -amount
                    direction = "out"
                else:
                    signed = amount
                    direction = "in"
                rows.append({
                    "date": payment.date,
                    "name": payment.name or method_name or _("دفعة"),
                    "reference": payment.memo or payment.payment_reference or "",
                    "channel": channel,
                    "direction": direction,
                    "amount": abs(amount),
                    "signed_amount": signed,
                    "partner_id": payment.partner_id.id,
                    "payment_id": payment.id,
                    "pos_payment_id": False,
                    "journal_id": payment.journal_id.id,
                    "is_matched": bool(
                        self.env["homeblend.payment.settle.book"].search_count([
                            ("matched_payment_id", "=", payment.id),
                            ("state", "=", "matched"),
                        ])
                    ),
                })

        if self.include_pos_payments and "pos.payment" in self.env:
            pos_domain = [
                ("session_id.company_id", "=", company.id),
                ("payment_date", ">=", fields.Datetime.to_datetime(date_from)),
                ("payment_date", "<", fields.Datetime.to_datetime(date_to + timedelta(days=1))),
            ]
            pos_payments = self.env["pos.payment"].sudo().search(pos_domain)
            for pos_pay in pos_payments:
                if float_is_zero(pos_pay.amount, precision_rounding=self.currency_id.rounding):
                    continue
                method = pos_pay.payment_method_id
                if method.type == "pay_later":
                    continue
                method_name = method.name or ""
                journal_type = method.journal_id.type if method.journal_id else None
                channel = _channel_from_text(method_name, journal_type)
                if method.type == "cash":
                    channel = "cash"
                elif method.type == "bank" and channel == "other":
                    channel = "bank"
                if not self._channel_ok(channel):
                    continue
                if self.journal_id and method.journal_id and method.journal_id != self.journal_id:
                    continue
                amount = pos_pay.amount
                direction = "in" if amount >= 0 else "out"
                rows.append({
                    "date": fields.Datetime.context_timestamp(self, pos_pay.payment_date).date()
                    if pos_pay.payment_date else date_from,
                    "name": "%s — %s" % (pos_pay.pos_order_id.name or _("POS"), method_name),
                    "reference": pos_pay.pos_order_id.pos_reference or "",
                    "channel": channel,
                    "direction": direction,
                    "amount": abs(amount),
                    "signed_amount": amount,
                    "partner_id": pos_pay.partner_id.id if pos_pay.partner_id else False,
                    "payment_id": False,
                    "pos_payment_id": pos_pay.id,
                    "journal_id": method.journal_id.id if method.journal_id else False,
                    "is_matched": bool(
                        self.env["homeblend.payment.settle.book"].search_count([
                            ("matched_pos_payment_id", "=", pos_pay.id),
                            ("state", "=", "matched"),
                        ])
                    ),
                })
        return rows

    def _book_domain(self):
        self.ensure_one()
        domain = [
            ("company_id", "=", self.company_id.id),
            ("date", ">=", self.date_from),
            ("date", "<=", self.date_to),
            ("state", "!=", "cancel"),
        ]
        if not self.include_matched_books:
            domain.append(("state", "=", "open"))
        if self.channel != "all":
            domain.append(("channel", "=", self.channel))
        if self.journal_id:
            domain += ["|", ("journal_id", "=", False), ("journal_id", "=", self.journal_id.id)]
        return domain

    def _rebuild(self):
        self.ensure_one()
        system_rows = self._system_rows()
        books = self.env["homeblend.payment.settle.book"].search(self._book_domain())
        system_lines = []
        for index, row in enumerate(system_rows, start=1):
            system_lines.append({
                "sequence": index,
                **row,
                "selected": False,
            })
        book_lines = []
        for index, book in enumerate(books, start=1):
            signed = book.amount if book.direction == "in" else -book.amount
            book_lines.append({
                "sequence": index,
                "book_id": book.id,
                "date": book.date,
                "name": book.name,
                "reference": book.reference or "",
                "channel": book.channel,
                "direction": book.direction,
                "amount": abs(book.amount),
                "signed_amount": signed,
                "is_matched": book.state == "matched",
                "selected": False,
            })
        self.system_line_ids = [Command.clear()] + [Command.create(vals) for vals in system_lines]
        self.book_line_ids = [Command.clear()] + [Command.create(vals) for vals in book_lines]
        system_total = sum(self.system_line_ids.mapped("signed_amount"))
        book_total = sum(self.book_line_ids.mapped("signed_amount"))
        self.write({
            "system_total": system_total,
            "book_total": book_total,
            "difference": system_total - book_total,
            "matched_count": len(self.system_line_ids.filtered("is_matched")),
            "unmatched_system_count": len(self.system_line_ids.filtered(lambda line: not line.is_matched)),
            "unmatched_book_count": len(self.book_line_ids.filtered(lambda line: not line.is_matched)),
        })

    def _apply_match(self, system_line, book_line, note=""):
        book = book_line.book_id
        if not book:
            raise UserError(_("سطر الكشف غير محفوظ."))
        vals = {
            "state": "matched",
            "match_note": note,
            "matched_payment_id": system_line.payment_id.id if system_line.payment_id else False,
            "matched_pos_payment_id": system_line.pos_payment_id.id if system_line.pos_payment_id else False,
        }
        book.write(vals)

    def _auto_match(self):
        self.ensure_one()
        currency = self.currency_id
        open_books = self.env["homeblend.payment.settle.book"].search(
            self._book_domain() + [("state", "=", "open")]
        )
        used_payment_ids = set(
            self.env["homeblend.payment.settle.book"].search([
                ("state", "=", "matched"),
                ("matched_payment_id", "!=", False),
            ]).mapped("matched_payment_id").ids
        )
        used_pos_ids = set(
            self.env["homeblend.payment.settle.book"].search([
                ("state", "=", "matched"),
                ("matched_pos_payment_id", "!=", False),
            ]).mapped("matched_pos_payment_id").ids
        )
        system_rows = []
        for row in self._system_rows():
            if row["payment_id"] and row["payment_id"] in used_payment_ids:
                continue
            if row["pos_payment_id"] and row["pos_payment_id"] in used_pos_ids:
                continue
            if row["is_matched"]:
                continue
            system_rows.append(row)

        for book in open_books:
            candidates = []
            for row in system_rows:
                if row.get("_used"):
                    continue
                if row["channel"] != book.channel and self.channel == "all":
                    # still allow same-direction amount match across channel only if channel filter is all? Prefer same channel
                    if row["channel"] != book.channel:
                        continue
                if row["direction"] != book.direction:
                    continue
                if float_compare(row["amount"], abs(book.amount), precision_rounding=currency.rounding) != 0:
                    continue
                day_gap = abs((row["date"] - book.date).days)
                if day_gap > 3:
                    continue
                ref_bonus = 0
                book_ref = (book.reference or "").strip().lower()
                sys_ref = (row["reference"] or "").strip().lower()
                if book_ref and sys_ref and (book_ref in sys_ref or sys_ref in book_ref):
                    ref_bonus = -10
                candidates.append((day_gap + ref_bonus, row))
            if not candidates:
                continue
            candidates.sort(key=lambda item: item[0])
            best = candidates[0][1]
            best["_used"] = True
            # create a fake system line browse via temporary write on book
            SystemProxy = type("SystemProxy", (), {})
            proxy = SystemProxy()
            proxy.payment_id = self.env["account.payment"].browse(best["payment_id"]) if best["payment_id"] else self.env["account.payment"]
            proxy.pos_payment_id = self.env["pos.payment"].browse(best["pos_payment_id"]) if best["pos_payment_id"] else self.env["pos.payment"]
            BookProxy = type("BookProxy", (), {"book_id": book})
            self._apply_match(proxy, BookProxy(), note="مطابقة تلقائية")


class HomeblendPaymentSettleSystem(models.TransientModel):
    _name = "homeblend.payment.settle.system"
    _description = "سطر نظام لتسوية المدفوعات"
    _order = "date, sequence, id"

    settle_id = fields.Many2one("homeblend.payment.settle", required=True, ondelete="cascade")
    currency_id = fields.Many2one(related="settle_id.currency_id")
    sequence = fields.Integer()
    selected = fields.Boolean(string="اختيار")
    date = fields.Date(string="التاريخ")
    name = fields.Char(string="البيان")
    reference = fields.Char(string="المرجع")
    channel = fields.Selection(CHANNEL_SELECTION[1:], string="الوسيلة")
    direction = fields.Selection([("in", "وارد"), ("out", "صادر")], string="الاتجاه")
    amount = fields.Monetary(string="المبلغ")
    signed_amount = fields.Monetary(string="المبلغ موقّع")
    partner_id = fields.Many2one("res.partner", string="الشريك")
    payment_id = fields.Many2one("account.payment", string="الدفعة")
    pos_payment_id = fields.Many2one("pos.payment", string="دفعة POS")
    journal_id = fields.Many2one("account.journal", string="الدفتر")
    is_matched = fields.Boolean(string="مسوّى")


class HomeblendPaymentSettleLine(models.TransientModel):
    _name = "homeblend.payment.settle.line"
    _description = "سطر كشف معروض في التسوية"
    _order = "date, sequence, id"

    settle_id = fields.Many2one("homeblend.payment.settle", required=True, ondelete="cascade")
    currency_id = fields.Many2one(related="settle_id.currency_id")
    book_id = fields.Many2one("homeblend.payment.settle.book", string="سطر الكشف")
    sequence = fields.Integer()
    selected = fields.Boolean(string="اختيار")
    date = fields.Date(string="التاريخ")
    name = fields.Char(string="البيان")
    reference = fields.Char(string="المرجع")
    channel = fields.Selection(CHANNEL_SELECTION[1:], string="الوسيلة")
    direction = fields.Selection([("in", "وارد"), ("out", "صادر")], string="الاتجاه")
    amount = fields.Monetary(string="المبلغ")
    signed_amount = fields.Monetary(string="المبلغ موقّع")
    is_matched = fields.Boolean(string="مسوّى")
