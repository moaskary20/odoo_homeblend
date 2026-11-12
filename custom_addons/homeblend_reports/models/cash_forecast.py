from datetime import timedelta

from odoo import api, fields, models
from odoo.fields import Command


class HomeblendCashForecastExpected(models.Model):
    _name = "homeblend.cash.forecast.expected"
    _description = "تدفق نقدي متوقع"
    _order = "date, id"

    name = fields.Char(string="البيان", required=True)
    date = fields.Date(string="التاريخ المتوقع", required=True, index=True)
    direction = fields.Selection(
        [("in", "وارد"), ("out", "صادر")],
        string="الاتجاه",
        required=True,
        default="in",
    )
    amount = fields.Monetary(string="المبلغ", required=True)
    currency_id = fields.Many2one(related="company_id.currency_id")
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
    )
    account_id = fields.Many2one(
        "account.account",
        string="البنك / الصندوق",
        domain="[('account_type', '=', 'asset_cash'), ('company_ids', 'in', company_id)]",
    )
    state = fields.Selection(
        [("planned", "مخطط"), ("done", "تم"), ("cancel", "ملغى")],
        default="planned",
        required=True,
    )


class HomeblendCashForecast(models.TransientModel):
    _name = "homeblend.cash.forecast"
    _inherit = ["homeblend.xlsx.export.mixin"]
    _description = "التنبؤ بالرصيد البنكي"

    name = fields.Char(compute="_compute_name")
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self._default_company(),
    )
    currency_id = fields.Many2one(related="company_id.currency_id")
    account_id = fields.Many2one(
        "account.account",
        string="بنك / صندوق محدد",
        domain="[('account_type', '=', 'asset_cash'), ('company_ids', 'in', company_id)]",
        help="اتركه فارغاً للتنبؤ بإجمالي النقدية والبنوك.",
    )
    date_from = fields.Date(required=True, default=fields.Date.context_today)
    horizon_days = fields.Selection(
        [("30", "30 يوماً"), ("60", "60 يوماً"), ("90", "90 يوماً")],
        string="الأفق",
        default="30",
        required=True,
    )
    min_balance = fields.Monetary(
        string="الحد الأدنى للتنبيه",
        help="إذا نزل الرصيد المتوقع عن هذا الحد يُعلَّم اليوم باللون التحذيري.",
    )
    include_receivables = fields.Boolean(string="مستحقات العملاء", default=True)
    include_payables = fields.Boolean(string="مستحقات الموردين", default=True)
    include_manual = fields.Boolean(string="التدفقات المخططة يدوياً", default=True)
    opening_balance = fields.Monetary(string="الرصيد الحالي", readonly=True)
    closing_balance = fields.Monetary(string="الرصيد في نهاية الأفق", readonly=True)
    lowest_balance = fields.Monetary(string="أدنى رصيد متوقع", readonly=True)
    total_inflow = fields.Monetary(string="إجمالي الوارد المتوقع", readonly=True)
    total_outflow = fields.Monetary(string="إجمالي الصادر المتوقع", readonly=True)
    alert_days = fields.Integer(string="أيام تحت الحد الأدنى", readonly=True)
    line_ids = fields.One2many("homeblend.cash.forecast.line", "forecast_id")
    flow_ids = fields.One2many("homeblend.cash.forecast.flow", "forecast_id")

    @api.model
    def _default_company(self):
        company = self.env["res.company"].search(
            [("name", "ilike", "home"), ("name", "ilike", "blend")],
            limit=1,
        )
        return company or self.env.company

    @api.depends("date_from", "horizon_days", "account_id")
    def _compute_name(self):
        for forecast in self:
            account = forecast.account_id.display_name if forecast.account_id else "إجمالي النقدية"
            forecast.name = "تنبؤ الرصيد — %s — %s يوم من %s" % (
                account,
                forecast.horizon_days or "30",
                forecast.date_from or "",
            )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records.action_compute()
        return records

    def write(self, vals):
        res = super().write(vals)
        watched = {
            "date_from", "horizon_days", "company_id", "account_id", "min_balance",
            "include_receivables", "include_payables", "include_manual",
        }
        if watched & set(vals):
            self.action_compute()
        return res

    def action_open_manual_flows(self):
        self.ensure_one()
        action = {
            "type": "ir.actions.act_window",
            "name": "تدفقات نقدية مخططة",
            "res_model": "homeblend.cash.forecast.expected",
            "view_mode": "list,form",
            "domain": [("company_id", "=", self.company_id.id), ("state", "=", "planned")],
            "context": {
                "default_company_id": self.company_id.id,
                "default_account_id": self.account_id.id,
            },
        }
        return action

    def action_compute(self):
        for forecast in self:
            forecast._rebuild()
        return True

    def action_export_xlsx(self):
        self.ensure_one()
        if not self.line_ids:
            self.action_compute()
        day_rows = [
            {
                "kind": "alert" if line.is_alert else None,
                "values": [
                    line.date.isoformat() if line.date else "",
                    line.inflow or 0.0,
                    line.outflow or 0.0,
                    line.balance or 0.0,
                    "تنبيه" if line.is_alert else "",
                ],
            }
            for line in self.line_ids
        ]
        source_labels = dict(self.env["homeblend.cash.forecast.flow"]._fields["source"].selection)
        direction_labels = dict(self.env["homeblend.cash.forecast.flow"]._fields["direction"].selection)
        flow_rows = [
            [
                flow.date.isoformat() if flow.date else "",
                flow.name or "",
                source_labels.get(flow.source, flow.source or ""),
                direction_labels.get(flow.direction, flow.direction or ""),
                flow.amount or 0.0,
                flow.partner_id.display_name if flow.partner_id else "",
            ]
            for flow in self.flow_ids
        ]
        return self._hb_xlsx_download(
            self.name or "cash_forecast",
            [
                {
                    "name": "الرصيد اليومي",
                    "title": self.name,
                    "meta": [
                        "الشركة: %s" % (self.company_id.name or ""),
                        "الرصيد الحالي: %.2f" % (self.opening_balance or 0.0),
                        "الرصيد النهائي: %.2f" % (self.closing_balance or 0.0),
                        "أدنى رصيد: %.2f" % (self.lowest_balance or 0.0),
                    ],
                    "headers": ["اليوم", "وارد", "صادر", "الرصيد المتوقع", "تنبيه"],
                    "rows": day_rows,
                },
                {
                    "name": "تفصيل التدفقات",
                    "title": "تفصيل التدفقات",
                    "headers": ["التاريخ", "البيان", "المصدر", "الاتجاه", "المبلغ", "الشريك"],
                    "rows": flow_rows,
                },
            ],
        )

    def action_print_pdf(self):
        self.ensure_one()
        if not self.line_ids:
            self.action_compute()
        return self.env.ref("homeblend_reports.action_report_hb_cash_forecast_pdf").report_action(self)

    def _cash_accounts(self):
        self.ensure_one()
        Account = self.env["account.account"].with_company(self.company_id)
        domain = [
            ("account_type", "=", "asset_cash"),
            ("company_ids", "in", self.company_id.id),
        ]
        if self.account_id:
            domain.append(("id", "=", self.account_id.id))
        return Account.search(domain)

    def _opening_balance(self):
        self.ensure_one()
        accounts = self._cash_accounts()
        if not accounts:
            return 0.0
        # رصيد حتى نهاية يوم قبل البداية = حركة حتى date_from - 1، وإلا حتى اليوم inclusive لـ date_from
        date_to = self.date_from
        lines = self.env["account.move.line"].sudo().search([
            ("parent_state", "=", "posted"),
            ("company_id", "=", self.company_id.id),
            ("account_id", "in", accounts.ids),
            ("date", "<=", date_to),
            ("display_type", "not in", ["line_section", "line_note"]),
        ])
        return sum(lines.mapped("balance"))

    def _collect_flows(self):
        self.ensure_one()
        flows = []
        date_from = self.date_from
        date_to = date_from + timedelta(days=int(self.horizon_days) - 1)
        Move = self.env["account.move"].sudo().with_company(self.company_id)

        if self.include_receivables:
            invoices = Move.search([
                ("company_id", "=", self.company_id.id),
                ("move_type", "=", "out_invoice"),
                ("state", "=", "posted"),
                ("payment_state", "in", ["not_paid", "partial"]),
                ("amount_residual", ">", 0),
            ])
            for move in invoices:
                due = move.invoice_date_due or move.invoice_date or date_from
                if due < date_from:
                    due = date_from
                if due > date_to:
                    continue
                flows.append({
                    "date": due,
                    "direction": "in",
                    "amount": move.amount_residual,
                    "source": "receivable",
                    "name": "تحصيل متوقع: %s" % (move.name or move.partner_id.display_name or ""),
                    "partner_id": move.partner_id.id,
                    "move_id": move.id,
                })

        if self.include_payables:
            bills = Move.search([
                ("company_id", "=", self.company_id.id),
                ("move_type", "=", "in_invoice"),
                ("state", "=", "posted"),
                ("payment_state", "in", ["not_paid", "partial"]),
                ("amount_residual", ">", 0),
            ])
            for move in bills:
                due = move.invoice_date_due or move.invoice_date or date_from
                if due < date_from:
                    due = date_from
                if due > date_to:
                    continue
                flows.append({
                    "date": due,
                    "direction": "out",
                    "amount": abs(move.amount_residual),
                    "source": "payable",
                    "name": "سداد متوقع: %s" % (move.name or move.partner_id.display_name or ""),
                    "partner_id": move.partner_id.id,
                    "move_id": move.id,
                })

        if self.include_manual:
            domain = [
                ("company_id", "=", self.company_id.id),
                ("state", "=", "planned"),
                ("date", ">=", date_from),
                ("date", "<=", date_to),
            ]
            if self.account_id:
                domain += ["|", ("account_id", "=", False), ("account_id", "=", self.account_id.id)]
            for row in self.env["homeblend.cash.forecast.expected"].search(domain):
                flows.append({
                    "date": row.date,
                    "direction": row.direction,
                    "amount": abs(row.amount),
                    "source": "manual",
                    "name": row.name,
                    "partner_id": False,
                    "move_id": False,
                })
        return flows

    def _rebuild(self):
        self.ensure_one()
        opening = self._opening_balance()
        flows = self._collect_flows()
        days = int(self.horizon_days)
        by_date = {}
        for flow in flows:
            by_date.setdefault(flow["date"], []).append(flow)

        day_lines = []
        flow_lines = []
        balance = opening
        total_in = 0.0
        total_out = 0.0
        lowest = opening
        alert_days = 0
        sequence = 0
        for offset in range(days):
            day = self.date_from + timedelta(days=offset)
            day_in = 0.0
            day_out = 0.0
            for flow in by_date.get(day, []):
                sequence += 1
                amount = flow["amount"]
                if flow["direction"] == "in":
                    day_in += amount
                    total_in += amount
                else:
                    day_out += amount
                    total_out += amount
                flow_lines.append({
                    "sequence": sequence,
                    "date": day,
                    "name": flow["name"],
                    "source": flow["source"],
                    "direction": flow["direction"],
                    "amount": amount,
                    "partner_id": flow["partner_id"],
                    "move_id": flow["move_id"],
                })
            balance = balance + day_in - day_out
            lowest = min(lowest, balance)
            below = bool(self.min_balance) and balance < self.min_balance
            if below:
                alert_days += 1
            day_lines.append({
                "sequence": offset + 1,
                "date": day,
                "inflow": day_in,
                "outflow": day_out,
                "balance": balance,
                "is_alert": below,
            })

        self.line_ids = [Command.clear()] + [Command.create(vals) for vals in day_lines]
        self.flow_ids = [Command.clear()] + [Command.create(vals) for vals in flow_lines]
        self.write({
            "opening_balance": opening,
            "closing_balance": balance,
            "lowest_balance": lowest,
            "total_inflow": total_in,
            "total_outflow": total_out,
            "alert_days": alert_days,
        })


class HomeblendCashForecastLine(models.TransientModel):
    _name = "homeblend.cash.forecast.line"
    _description = "سطر يومي لتنبؤ الرصيد"
    _order = "sequence, id"

    forecast_id = fields.Many2one("homeblend.cash.forecast", required=True, ondelete="cascade")
    currency_id = fields.Many2one(related="forecast_id.currency_id")
    sequence = fields.Integer()
    date = fields.Date(string="اليوم")
    inflow = fields.Monetary(string="وارد")
    outflow = fields.Monetary(string="صادر")
    balance = fields.Monetary(string="الرصيد المتوقع")
    is_alert = fields.Boolean(string="تحت الحد")


class HomeblendCashForecastFlow(models.TransientModel):
    _name = "homeblend.cash.forecast.flow"
    _description = "تفصيل تدفق متوقع"
    _order = "date, sequence, id"

    forecast_id = fields.Many2one("homeblend.cash.forecast", required=True, ondelete="cascade")
    currency_id = fields.Many2one(related="forecast_id.currency_id")
    sequence = fields.Integer()
    date = fields.Date(string="التاريخ")
    name = fields.Char(string="البيان")
    source = fields.Selection(
        [
            ("receivable", "عملاء"),
            ("payable", "موردون"),
            ("manual", "يدوي"),
        ],
        string="المصدر",
    )
    direction = fields.Selection([("in", "وارد"), ("out", "صادر")], string="الاتجاه")
    amount = fields.Monetary(string="المبلغ")
    partner_id = fields.Many2one("res.partner", string="الشريك")
    move_id = fields.Many2one("account.move", string="المستند")
