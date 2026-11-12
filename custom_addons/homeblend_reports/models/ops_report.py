from odoo import api, fields, models
from odoo.fields import Command


REPORT_TYPES = [
    ("receivables", "الذمم المدينة"),
    ("payables", "الذمم الدائنة"),
    ("cashflow", "التدفقات النقدية"),
    ("taxes", "الضرائب"),
    ("income", "تفصيل الإيرادات"),
    ("expense", "تفصيل المصروفات"),
]


class HomeblendOpsReport(models.TransientModel):
    _name = "homeblend.ops.report"
    _inherit = ["homeblend.xlsx.export.mixin"]
    _description = "تقرير محاسبي قابل للتصدير"

    name = fields.Char(compute="_compute_name")
    report_type = fields.Selection(REPORT_TYPES, required=True, default="receivables")
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(related="company_id.currency_id")
    date_from = fields.Date(
        string="من",
        required=True,
        default=lambda self: fields.Date.context_today(self).replace(month=1, day=1),
    )
    date_to = fields.Date(string="إلى", required=True, default=fields.Date.context_today)
    line_ids = fields.One2many("homeblend.ops.report.line", "report_id")
    total_amount = fields.Monetary(string="الإجمالي", readonly=True)

    @api.depends("report_type", "date_from", "date_to")
    def _compute_name(self):
        labels = dict(REPORT_TYPES)
        for rec in self:
            rec.name = "%s — من %s إلى %s" % (
                labels.get(rec.report_type, "تقرير"),
                rec.date_from or "",
                rec.date_to or "",
            )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records.action_compute()
        return records

    def write(self, vals):
        res = super().write(vals)
        if {"report_type", "company_id", "date_from", "date_to"} & set(vals):
            self.action_compute()
        return res

    def action_compute(self):
        for report in self:
            report._rebuild()
        return True

    def action_export_xlsx(self):
        self.ensure_one()
        if not self.line_ids:
            self.action_compute()
        rows = []
        for line in self.line_ids:
            rows.append({
                "kind": "total" if line.is_total else None,
                "values": [
                    line.date.isoformat() if line.date else "",
                    line.name or "",
                    line.partner_id.display_name if line.partner_id else "",
                    line.account_id.display_name if line.account_id else "",
                    line.debit or 0.0,
                    line.credit or 0.0,
                    line.balance or 0.0,
                    line.residual or 0.0,
                ],
            })
        return self._hb_xlsx_download(
            self.name or "ops_report",
            [{
                "name": dict(REPORT_TYPES).get(self.report_type, "تقرير"),
                "title": self.name,
                "meta": ["الشركة: %s" % (self.company_id.name or "")],
                "headers": [
                    "التاريخ", "البيان", "الشريك", "الحساب",
                    "مدين", "دائن", "الرصيد", "المتبقي",
                ],
                "rows": rows,
                "notes": ["الإجمالي: %.2f" % (self.total_amount or 0.0)],
            }],
        )

    def action_print_pdf(self):
        self.ensure_one()
        if not self.line_ids:
            self.action_compute()
        return self.env.ref("homeblend_reports.action_report_hb_ops_pdf").report_action(self)

    def _rebuild(self):
        self.ensure_one()
        rows = []
        total = 0.0
        if self.report_type in ("receivables", "payables"):
            move_type = "out_invoice" if self.report_type == "receivables" else "in_invoice"
            moves = self.env["account.move"].sudo().search([
                ("company_id", "=", self.company_id.id),
                ("move_type", "=", move_type),
                ("state", "=", "posted"),
                ("payment_state", "in", ["not_paid", "partial"]),
                ("invoice_date", ">=", self.date_from),
                ("invoice_date", "<=", self.date_to),
            ], order="invoice_date, name")
            for move in moves:
                residual = abs(move.amount_residual)
                total += residual
                rows.append({
                    "date": move.invoice_date or move.date,
                    "name": move.name,
                    "partner_id": move.partner_id.id,
                    "account_id": False,
                    "debit": move.amount_total_signed if move.amount_total_signed > 0 else 0.0,
                    "credit": abs(move.amount_total_signed) if move.amount_total_signed < 0 else 0.0,
                    "balance": move.amount_total_signed,
                    "residual": residual,
                })
        else:
            domain = [
                ("parent_state", "=", "posted"),
                ("company_id", "=", self.company_id.id),
                ("display_type", "not in", ["line_section", "line_note"]),
                ("date", ">=", self.date_from),
                ("date", "<=", self.date_to),
            ]
            if self.report_type == "cashflow":
                domain.append(("account_id.account_type", "=", "asset_cash"))
            elif self.report_type == "taxes":
                domain.append(("tax_line_id", "!=", False))
            elif self.report_type == "income":
                domain.append(("account_id.account_type", "in", ["income", "income_other"]))
            elif self.report_type == "expense":
                domain.append((
                    "account_id.account_type",
                    "in",
                    ["expense", "expense_other", "expense_depreciation", "expense_direct_cost"],
                ))
            lines = self.env["account.move.line"].sudo().search(domain, order="date, id", limit=5000)
            for line in lines:
                total += line.balance
                rows.append({
                    "date": line.date,
                    "name": line.move_id.name or line.name or "",
                    "partner_id": line.partner_id.id,
                    "account_id": line.account_id.id,
                    "debit": line.debit,
                    "credit": line.credit,
                    "balance": line.balance,
                    "residual": abs(line.amount_residual) if "amount_residual" in line._fields else 0.0,
                })
        if rows:
            debit_sum = sum(r.get("debit") or 0.0 for r in rows)
            credit_sum = sum(r.get("credit") or 0.0 for r in rows)
            residual_sum = sum(r.get("residual") or 0.0 for r in rows)
            rows.append({
                "date": False,
                "name": "⟸ إجمالي · الإجمالي",
                "partner_id": False,
                "account_id": False,
                "debit": debit_sum,
                "credit": credit_sum,
                "balance": total,
                "residual": residual_sum,
                "is_total": True,
                "is_negative": total < 0,
            })
        self.line_ids = [Command.clear()] + [Command.create(vals) for vals in rows]
        self.total_amount = total


class HomeblendOpsReportLine(models.TransientModel):
    _name = "homeblend.ops.report.line"
    _description = "سطر تقرير محاسبي"
    _order = "is_total, date, id"

    report_id = fields.Many2one("homeblend.ops.report", required=True, ondelete="cascade")
    currency_id = fields.Many2one(related="report_id.currency_id")
    date = fields.Date(string="التاريخ")
    name = fields.Char(string="البيان")
    partner_id = fields.Many2one("res.partner", string="الشريك")
    account_id = fields.Many2one("account.account", string="الحساب")
    debit = fields.Monetary(string="مدين")
    credit = fields.Monetary(string="دائن")
    balance = fields.Monetary(string="الرصيد")
    residual = fields.Monetary(string="المتبقي")
    is_total = fields.Boolean()
    is_negative = fields.Boolean()
