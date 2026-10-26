from datetime import date, timedelta

from odoo import api, fields, models
from odoo.fields import Command

from .account_chart import CREDIT_TYPES

INCOME_BLOCKS = [
    ("header", "إيرادات النشاط", None),
    ("accounts", "pl_revenue_activity", "إيرادات النشاط"),
    ("total", "إجمالي إيرادات النشاط", ["pl_revenue_activity"]),
    ("header", "يطرح: تكاليف ومصاريف النشاط", None),
    ("accounts", "pl_cost_indirect", "تكاليف العمليات غير المباشرة"),
    ("accounts", "pl_cost_wages", "أجور ومرتبات"),
    ("accounts", "pl_cost_overhead", "مصروفات عمومية للعمليات"),
    ("accounts", "pl_cost_depr", "إهلاكات"),
    ("total", "إجمالي تكاليف النشاط", ["pl_cost_indirect", "pl_cost_wages", "pl_cost_overhead", "pl_cost_depr"]),
    ("result", "مجمل ربح النشاط", "activity"),
    ("header", "يضاف: إيرادات أخرى", None),
    ("accounts", "pl_other_income", "إيرادات متنوعة"),
    ("accounts", "pl_bank_income", "فوائد بنكية"),
    ("result", "مجمل الربح أو الخسارة", "gross"),
    ("header", "يطرح: المصروفات العمومية والإدارية", None),
    ("accounts", "pl_marketing", "مصاريف تسويقية"),
    ("accounts", "pl_fx", "فروق أسعار عملة"),
    ("accounts", "pl_admin_wages", "أجور ومرتبات وما في حكمها"),
    ("accounts", "pl_admin_leave", "مخصصات إجازات ونهاية خدمة"),
    ("accounts", "pl_admin_depr", "إهلاكات إدارية"),
    ("accounts", "pl_admin_general", "مصاريف إدارية وعامة"),
    ("accounts", "pl_admin_fees", "أتعاب محاسبية وقانونية"),
    ("total", "إجمالي المصروفات العمومية والإدارية", [
        "pl_marketing", "pl_fx", "pl_admin_wages", "pl_admin_leave",
        "pl_admin_depr", "pl_admin_general", "pl_admin_fees",
    ]),
    ("result", "صافي أرباح أو خسائر العام", "net"),
]

BALANCE_BLOCKS = [
    ("header", "الأصول", None),
    ("header", "الأصول المتداولة", None),
    ("accounts", "bs_cash", "نقدية بالبنوك والخزينة"),
    ("accounts", "bs_receivable", "مدينون وأرصدة مدينة أخرى"),
    ("accounts", "bs_related_asset", "شركات شقيقة وذات صلة"),
    ("accounts", "bs_inventory", "المخازن"),
    ("total", "مجموع الأصول المتداولة", ["bs_cash", "bs_receivable", "bs_related_asset", "bs_inventory"]),
    ("accounts", "bs_fixed_net", "الأصول الثابتة والممتلكات (بالصافي)"),
    ("accounts", "bs_other_asset", "أصول أخرى"),
    ("accounts", "bs_residual_asset", "أصول غير مبوبة"),
    ("total", "مجموع الأصول", ["__assets__"]),
    ("header", "الخصوم وحقوق الشركاء", None),
    ("header", "الخصوم المتداولة الأخرى", None),
    ("accounts", "bs_payable", "دائنون وأرصدة دائنة أخرى"),
    ("accounts", "bs_related_liability", "شركات شقيقة وذات صلة"),
    ("accounts", "bs_advances", "دفعات محصلة من الغير"),
    ("accounts", "bs_provision", "مخصصات"),
    ("accounts", "bs_statutory", "التزامات نظامية"),
    ("accounts", "bs_residual_liability", "خصوم غير مبوبة"),
    ("total", "مجموع الخصوم", ["bs_payable", "bs_related_liability", "bs_advances", "bs_provision", "bs_statutory", "bs_residual_liability"]),
    ("header", "حقوق الشركاء", None),
    ("accounts", "eq_capital", "رأس المال"),
    ("accounts", "eq_partner_buy", "جاري الشركاء شراء"),
    ("accounts", "eq_partner_sell", "جاري الشركاء بيع"),
    ("accounts", "eq_retained", "أرباح وخسائر مرحلة"),
    ("accounts", "bs_residual_equity", "حقوق ملكية غير مبوبة"),
    ("result", "صافي أرباح أو خسائر العام", "profit"),
    ("total", "صافي حقوق الشركاء", ["__equity__"]),
    ("total", "مجموع الخصوم وحقوق الشركاء", ["__liab_equity__"]),
]

COST_SECTIONS = ["pl_cost_indirect", "pl_cost_wages", "pl_cost_overhead", "pl_cost_depr"]
OVERHEAD_SECTIONS = [
    "pl_marketing", "pl_fx", "pl_admin_wages", "pl_admin_leave",
    "pl_admin_depr", "pl_admin_general", "pl_admin_fees",
]
INCOME_TYPES = {"income", "income_other"}
EXPENSE_TYPES = {"expense", "expense_other", "expense_depreciation", "expense_direct_cost"}
ASSET_TYPES = {
    "asset_receivable", "asset_cash", "asset_current", "asset_non_current",
    "asset_prepayments", "asset_fixed",
}
LIABILITY_TYPES = {
    "liability_payable", "liability_credit_card", "liability_current", "liability_non_current",
}
EQUITY_TYPES = {"equity", "equity_unaffected"}
ASSET_SECTIONS = ["bs_cash", "bs_receivable", "bs_related_asset", "bs_inventory", "bs_fixed", "bs_other_asset"]
LIABILITY_SECTIONS = [
    "bs_payable", "bs_related_liability", "bs_advances", "bs_provision", "bs_statutory", "bs_fixed_contra",
]
EQUITY_SECTIONS = ["eq_capital", "eq_retained", "eq_partner_buy", "eq_partner_sell"]


class HomeblendAccountStatement(models.TransientModel):
    _name = "homeblend.account.statement"
    _description = "قائمة حسابات هوم بليند"

    name = fields.Char(compute="_compute_name")
    report_type = fields.Selection(
        [
            ("trial", "ميزان المراجعة"),
            ("income", "قائمة الدخل"),
            ("balance", "الميزانية العمومية"),
        ],
        required=True,
        default="trial",
    )
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self._default_company())
    currency_id = fields.Many2one(related="company_id.currency_id")
    date_from = fields.Date(required=True, default=lambda self: fields.Date.context_today(self).replace(month=1, day=1))
    date_to = fields.Date(required=True, default=fields.Date.context_today)
    line_ids = fields.One2many("homeblend.account.statement.line", "statement_id")
    total_closing_debit = fields.Monetary()
    total_closing_credit = fields.Monetary()
    assets_total = fields.Monetary()
    liabilities_equity_total = fields.Monetary()
    activity_profit = fields.Monetary(string="مجمل ربح النشاط")
    net_profit = fields.Monetary(string="صافي الربح أو الخسارة")
    cost_ratio = fields.Float(string="نسبة التكلفة إلى الإيراد %", digits=(16, 2))
    overhead_ratio = fields.Float(string="نسبة المصروفات العمومية إلى الإيراد %", digits=(16, 2))
    difference = fields.Monetary(string="الفرق")
    is_balanced = fields.Boolean(string="متوازن")

    @api.model
    def _default_company(self):
        company = self.env["res.company"].search([("name", "ilike", "home"), ("name", "ilike", "blend")], limit=1)
        return company or self.env.company

    @api.depends("report_type", "date_from", "date_to")
    def _compute_name(self):
        labels = dict(self._fields["report_type"].selection)
        for statement in self:
            statement.name = "%s — %s إلى %s" % (
                labels.get(statement.report_type, ""),
                statement.date_from or "",
                statement.date_to or "",
            )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records.action_compute()
        return records

    def write(self, vals):
        res = super().write(vals)
        if {"date_from", "date_to", "company_id"} & set(vals):
            self.action_compute()
        return res

    def action_compute(self):
        for statement in self:
            builders = {
                "trial": statement._build_trial,
                "income": statement._build_income,
                "balance": statement._build_balance,
            }
            lines, totals = builders[statement.report_type]()
            statement.line_ids = [Command.clear()] + [Command.create(line) for line in lines]
            statement.write(totals)
        return True

    def _move_domain(self, date_from=None, date_to=None):
        domain = [
            ("parent_state", "=", "posted"),
            ("company_id", "=", self.company_id.id),
            ("display_type", "not in", ["line_section", "line_note"]),
        ]
        if date_from:
            domain.append(("date", ">=", date_from))
        if date_to:
            domain.append(("date", "<=", date_to))
        return domain

    def _sums_by_account(self, date_from=None, date_to=None):
        rows = self.env["account.move.line"]._read_group(
            self._move_domain(date_from, date_to),
            ["account_id"],
            ["debit:sum", "credit:sum"],
        )
        return {account.id: (debit or 0.0, credit or 0.0) for account, debit, credit in rows if account}

    def _split(self, amount):
        currency = self.company_id.currency_id
        if currency.is_zero(amount):
            return 0.0, 0.0
        if amount > 0:
            return amount, 0.0
        return 0.0, -amount

    def _build_trial(self):
        opening = self._sums_by_account(date_to=self.date_from - timedelta(days=1))
        period = self._sums_by_account(self.date_from, self.date_to)
        accounts = self.env["account.account"].with_company(self.company_id).search([
            ("company_ids", "in", self.company_id.id),
        ], order="code")
        lines = []
        total_debit = total_credit = 0.0
        sequence = 0
        for account in accounts:
            open_debit, open_credit = opening.get(account.id, (0.0, 0.0))
            per_debit, per_credit = period.get(account.id, (0.0, 0.0))
            open_net = open_debit - open_credit
            close_net = open_net + per_debit - per_credit
            if not any([open_debit, open_credit, per_debit, per_credit]):
                if not account.hb_chart:
                    continue
            open_d, open_c = self._split(open_net)
            close_d, close_c = self._split(close_net)
            total_debit += close_d
            total_credit += close_c
            sequence += 10
            lines.append({
                "sequence": sequence,
                "line_kind": "account",
                "code": account.code or "",
                "name": account.name,
                "nature": "دائن" if account.account_type in CREDIT_TYPES else "مدين",
                "opening_debit": open_d,
                "opening_credit": open_c,
                "period_debit": per_debit,
                "period_credit": per_credit,
                "closing_debit": close_d,
                "closing_credit": close_c,
            })
        difference = total_debit - total_credit
        sequence += 10
        lines.append({
            "sequence": sequence,
            "line_kind": "total",
            "is_total": True,
            "name": "الإجمالي",
            "closing_debit": total_debit,
            "closing_credit": total_credit,
            "amount": difference,
        })
        return lines, {
            "total_closing_debit": total_debit,
            "total_closing_credit": total_credit,
            "difference": difference,
            "is_balanced": self.company_id.currency_id.is_zero(difference),
        }

    def _section_amount(self, period_map, sections, sign=1):
        accounts = self.env["account.account"].with_company(self.company_id).search([
            ("company_ids", "in", self.company_id.id),
            ("hb_statement_section", "in", list(sections)),
        ])
        total = 0.0
        details = []
        for account in accounts.sorted("code"):
            debit, credit = period_map.get(account.id, (0.0, 0.0))
            amount = sign * (credit - debit if account.account_type in CREDIT_TYPES else debit - credit)
            if self.company_id.currency_id.is_zero(amount):
                continue
            details.append((account, amount))
            total += amount
        return total, details

    def _period_maps(self):
        current = self._sums_by_account(self.date_from, self.date_to)
        previous_from = date(self.date_from.year - 1, self.date_from.month, self.date_from.day)
        previous_to = date(self.date_to.year - 1, self.date_to.month, self.date_to.day)
        previous = self._sums_by_account(previous_from, previous_to)
        return current, previous

    def _stock_maps(self):
        current = self._sums_by_account(date_to=self.date_to)
        previous_to = date(self.date_to.year - 1, self.date_to.month, self.date_to.day)
        previous = self._sums_by_account(date_to=previous_to)
        return current, previous

    def _build_income(self):
        current, previous = self._period_maps()
        cache = {}
        cache_prev = {}
        lines = []
        sequence = 0

        def remember(section, current_map, store):
            total, details = self._section_amount(current_map, [section])
            store[section] = (total, details)
            return total, details

        for section in {block[1] for block in INCOME_BLOCKS if block[0] == "accounts"}:
            remember(section, current, cache)
            remember(section, previous, cache_prev)

        def money(sections, store):
            return sum(store.get(section, (0.0, []))[0] for section in sections)

        activity = money(["pl_revenue_activity"], cache)
        costs = money(COST_SECTIONS, cache)
        other = money(["pl_other_income", "pl_bank_income"], cache)
        overhead = money(OVERHEAD_SECTIONS, cache)
        activity_prev = money(["pl_revenue_activity"], cache_prev)
        costs_prev = money(COST_SECTIONS, cache_prev)
        other_prev = money(["pl_other_income", "pl_bank_income"], cache_prev)
        overhead_prev = money(OVERHEAD_SECTIONS, cache_prev)
        results = {
            "activity": (activity - costs, activity_prev - costs_prev),
            "gross": (activity - costs + other, activity_prev - costs_prev + other_prev),
            "net": (activity - costs + other - overhead, activity_prev - costs_prev + other_prev - overhead_prev),
        }
        uncategorized = self._uncategorized_income(current)
        uncategorized_prev = self._uncategorized_income(previous)

        for kind, title, payload in INCOME_BLOCKS:
            sequence += 10
            if kind == "header":
                lines.append({"sequence": sequence, "line_kind": "header", "name": title})
            elif kind == "accounts":
                total, details = cache.get(payload, (0.0, []))
                prev_total = cache_prev.get(payload, (0.0, []))[0]
                lines.append({
                    "sequence": sequence,
                    "line_kind": "header",
                    "name": title,
                    "amount": total,
                    "amount_compare": prev_total,
                })
                for account, amount in details:
                    sequence += 1
                    lines.append({
                        "sequence": sequence,
                        "line_kind": "account",
                        "code": account.code or "",
                        "name": account.name,
                        "amount": amount,
                    })
            elif kind == "total":
                lines.append({
                    "sequence": sequence,
                    "line_kind": "total",
                    "is_total": True,
                    "name": title,
                    "amount": money(payload, cache),
                    "amount_compare": money(payload, cache_prev),
                })
            else:
                amount, amount_prev = results[payload]
                lines.append({
                    "sequence": sequence,
                    "line_kind": "total",
                    "is_total": True,
                    "name": title,
                    "amount": amount,
                    "amount_compare": amount_prev,
                })
        if uncategorized or uncategorized_prev:
            sequence += 10
            lines.append({
                "sequence": sequence,
                "line_kind": "total",
                "is_total": True,
                "name": "بنود إيراد ومصروف غير مبوبة في الشجرة",
                "amount": uncategorized,
                "amount_compare": uncategorized_prev,
            })
            results["net"] = (results["net"][0] + uncategorized, results["net"][1] + uncategorized_prev)
            lines.append({
                "sequence": sequence + 1,
                "line_kind": "total",
                "is_total": True,
                "name": "صافي الربح بعد البنود غير المبوبة",
                "amount": results["net"][0],
                "amount_compare": results["net"][1],
            })
        revenue = activity or 0.0
        return lines, {
            "activity_profit": results["activity"][0],
            "net_profit": results["net"][0],
            "cost_ratio": (costs / revenue * 100.0) if revenue else 0.0,
            "overhead_ratio": (overhead / revenue * 100.0) if revenue else 0.0,
        }

    def _uncategorized_income(self, period_map):
        accounts = self.env["account.account"].with_company(self.company_id).search([
            ("company_ids", "in", self.company_id.id),
            ("account_type", "in", list(INCOME_TYPES | EXPENSE_TYPES)),
            ("hb_statement_section", "=", False),
        ])
        total = 0.0
        for account in accounts:
            debit, credit = period_map.get(account.id, (0.0, 0.0))
            total += credit - debit
        return total

    def _build_balance(self):
        current, previous = self._stock_maps()
        profit = self._profit_until(self.date_to)
        profit_prev = self._profit_until(date(self.date_to.year - 1, self.date_to.month, self.date_to.day))
        cache = {}
        cache_prev = {}
        sections = [
            "bs_cash", "bs_receivable", "bs_related_asset", "bs_inventory", "bs_fixed",
            "bs_fixed_contra", "bs_other_asset", "bs_payable", "bs_related_liability",
            "bs_advances", "bs_provision", "bs_statutory", "eq_capital", "eq_retained",
            "eq_partner_buy", "eq_partner_sell",
        ]
        for section in sections:
            cache[section] = self._section_amount(current, [section])
            cache_prev[section] = self._section_amount(previous, [section])
        fixed_net = cache["bs_fixed"][0] - cache["bs_fixed_contra"][0]
        fixed_net_prev = cache_prev["bs_fixed"][0] - cache_prev["bs_fixed_contra"][0]
        contra_details = [(account, -amount) for account, amount in cache["bs_fixed_contra"][1]]
        cache["bs_fixed_net"] = (fixed_net, cache["bs_fixed"][1] + contra_details)
        cache_prev["bs_fixed_net"] = (fixed_net_prev, [])
        cache["bs_residual_asset"] = self._residual_amount(current, ASSET_TYPES, ASSET_SECTIONS)
        cache["bs_residual_liability"] = self._residual_amount(current, LIABILITY_TYPES, LIABILITY_SECTIONS)
        cache["bs_residual_equity"] = self._residual_amount(current, EQUITY_TYPES, EQUITY_SECTIONS)
        cache_prev["bs_residual_asset"] = self._residual_amount(previous, ASSET_TYPES, ASSET_SECTIONS)
        cache_prev["bs_residual_liability"] = self._residual_amount(previous, LIABILITY_TYPES, LIABILITY_SECTIONS)
        cache_prev["bs_residual_equity"] = self._residual_amount(previous, EQUITY_TYPES, EQUITY_SECTIONS)
        current_assets = sum(cache[key][0] for key in ["bs_cash", "bs_receivable", "bs_related_asset", "bs_inventory"])
        assets = current_assets + fixed_net + cache["bs_other_asset"][0] + cache["bs_residual_asset"][0]
        liabilities = sum(cache[key][0] for key in ["bs_payable", "bs_related_liability", "bs_advances", "bs_provision", "bs_statutory", "bs_residual_liability"])
        equity = sum(cache[key][0] for key in ["eq_capital", "eq_retained", "eq_partner_buy", "eq_partner_sell", "bs_residual_equity"]) + profit
        current_assets_prev = sum(cache_prev[key][0] for key in ["bs_cash", "bs_receivable", "bs_related_asset", "bs_inventory"])
        assets_prev = current_assets_prev + fixed_net_prev + cache_prev["bs_other_asset"][0] + cache_prev["bs_residual_asset"][0]
        liabilities_prev = sum(cache_prev[key][0] for key in ["bs_payable", "bs_related_liability", "bs_advances", "bs_provision", "bs_statutory", "bs_residual_liability"])
        equity_prev = sum(cache_prev[key][0] for key in ["eq_capital", "eq_retained", "eq_partner_buy", "eq_partner_sell", "bs_residual_equity"]) + profit_prev
        totals = {
            "bs_cash": cache["bs_cash"][0],
            "bs_receivable": cache["bs_receivable"][0],
            "bs_related_asset": cache["bs_related_asset"][0],
            "bs_inventory": cache["bs_inventory"][0],
            "bs_fixed_net": fixed_net,
            "bs_other_asset": cache["bs_other_asset"][0],
            "bs_residual_asset": cache["bs_residual_asset"][0],
            "bs_residual_liability": cache["bs_residual_liability"][0],
            "bs_residual_equity": cache["bs_residual_equity"][0],
            "__assets__": assets,
            "bs_payable": cache["bs_payable"][0],
            "bs_related_liability": cache["bs_related_liability"][0],
            "bs_advances": cache["bs_advances"][0],
            "bs_provision": cache["bs_provision"][0],
            "bs_statutory": cache["bs_statutory"][0],
            "eq_capital": cache["eq_capital"][0],
            "eq_partner_buy": cache["eq_partner_buy"][0],
            "eq_partner_sell": cache["eq_partner_sell"][0],
            "eq_retained": cache["eq_retained"][0],
            "__equity__": equity,
            "__liab_equity__": liabilities + equity,
        }
        totals_prev = {
            "__assets__": assets_prev,
            "__equity__": equity_prev,
            "__liab_equity__": liabilities_prev + equity_prev,
            "bs_fixed_net": fixed_net_prev,
        }
        for key, (amount, _details) in cache_prev.items():
            totals_prev.setdefault(key, amount)
        lines = []
        sequence = 0
        for kind, title, payload in BALANCE_BLOCKS:
            sequence += 10
            if kind == "header":
                lines.append({"sequence": sequence, "line_kind": "header", "name": title})
                continue
            if kind == "result":
                lines.append({
                    "sequence": sequence,
                    "line_kind": "total",
                    "is_total": True,
                    "name": title,
                    "amount": profit,
                    "amount_compare": profit_prev,
                })
                continue
            if kind == "total":
                if payload == ["__assets__"]:
                    amount = assets
                    amount_prev = assets_prev
                elif payload == ["__equity__"]:
                    amount = equity
                    amount_prev = equity_prev
                elif payload == ["__liab_equity__"]:
                    amount = liabilities + equity
                    amount_prev = liabilities_prev + equity_prev
                else:
                    amount = sum(totals.get(key, 0.0) for key in payload)
                    amount_prev = sum(totals_prev.get(key, 0.0) for key in payload)
                lines.append({
                    "sequence": sequence,
                    "line_kind": "total",
                    "is_total": True,
                    "name": title,
                    "amount": amount,
                    "amount_compare": amount_prev,
                })
                continue
            amount = totals.get(payload, 0.0)
            amount_prev = totals_prev.get(payload, 0.0)
            details = cache.get(payload, (0.0, []))[1]
            if str(payload).startswith("bs_residual") and self.company_id.currency_id.is_zero(amount) and not details:
                continue
            lines.append({
                "sequence": sequence,
                "line_kind": "header",
                "name": title,
                "amount": amount,
                "amount_compare": amount_prev,
            })
            for account, detail_amount in details:
                sequence += 1
                lines.append({
                    "sequence": sequence,
                    "line_kind": "account",
                    "code": account.code or "",
                    "name": account.name,
                    "amount": detail_amount,
                })
        difference = assets - (liabilities + equity)
        return lines, {
            "assets_total": assets,
            "liabilities_equity_total": liabilities + equity,
            "net_profit": profit,
            "difference": difference,
            "is_balanced": self.company_id.currency_id.is_zero(difference),
        }

    def _residual_amount(self, period_map, account_types, used_sections):
        accounts = self.env["account.account"].with_company(self.company_id).search([
            ("company_ids", "in", self.company_id.id),
            ("account_type", "in", list(account_types)),
            "|",
            ("hb_statement_section", "=", False),
            ("hb_statement_section", "not in", list(used_sections)),
        ])
        total = 0.0
        details = []
        currency = self.company_id.currency_id
        for account in accounts.sorted("code"):
            debit, credit = period_map.get(account.id, (0.0, 0.0))
            amount = (credit - debit) if account.account_type in CREDIT_TYPES else (debit - credit)
            if currency.is_zero(amount):
                continue
            details.append((account, amount))
            total += amount
        return total, details

    def _profit_until(self, date_to):
        period = self._sums_by_account(date_to=date_to)
        accounts = self.env["account.account"].with_company(self.company_id).search([
            ("company_ids", "in", self.company_id.id),
            ("account_type", "in", list(INCOME_TYPES | EXPENSE_TYPES)),
        ])
        profit = 0.0
        for account in accounts:
            debit, credit = period.get(account.id, (0.0, 0.0))
            profit += credit - debit
        return profit


class HomeblendAccountStatementLine(models.TransientModel):
    _name = "homeblend.account.statement.line"
    _description = "سطر قائمة حسابات هوم بليند"
    _order = "sequence, id"

    statement_id = fields.Many2one("homeblend.account.statement", required=True, ondelete="cascade")
    currency_id = fields.Many2one(related="statement_id.currency_id")
    sequence = fields.Integer()
    line_kind = fields.Selection(
        [("header", "عنوان"), ("account", "حساب"), ("total", "إجمالي")],
        default="account",
    )
    is_total = fields.Boolean()
    code = fields.Char(string="الكود")
    name = fields.Char(string="البيان", required=True)
    nature = fields.Char(string="الطبيعة")
    opening_debit = fields.Monetary(string="أول المدة مدين")
    opening_credit = fields.Monetary(string="أول المدة دائن")
    period_debit = fields.Monetary(string="الحركة مدين")
    period_credit = fields.Monetary(string="الحركة دائن")
    closing_debit = fields.Monetary(string="آخر المدة مدين")
    closing_credit = fields.Monetary(string="آخر المدة دائن")
    amount = fields.Monetary(string="السنة")
    amount_compare = fields.Monetary(string="السنة السابقة")
