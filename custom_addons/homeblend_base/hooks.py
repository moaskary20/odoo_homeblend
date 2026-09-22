import logging
from datetime import date, datetime

from dateutil.relativedelta import relativedelta

from odoo.fields import Command

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    eg = env.ref("base.eg")
    egp = env.ref("base.EGP")
    main = env.ref("base.main_company")
    if "home blend" not in (main.name or "").lower():
        try:
            main.write({"name": "Home Blend"})
        except Exception:
            _logger.exception("Could not rename main company")
    art = env["res.company"].search([("name", "=", "Art Casa")], limit=1)
    if not art:
        art = env["res.company"].create({
            "name": "Art Casa",
            "country_id": eg.id,
            "currency_id": egp.id,
            "account_fiscal_country_id": eg.id,
        })
    admin = env.ref("base.user_admin")
    admin.write({
        "company_ids": [Command.link(main.id), Command.link(art.id)],
        "company_id": main.id,
        "group_ids": [Command.link(env.ref("base.group_multi_company").id)],
    })
    root = env.ref("base.user_root")
    root.write({
        "company_ids": [Command.link(main.id), Command.link(art.id)],
    })
    Chart = env["account.chart.template"]
    for company in (main | art):
        try:
            Chart.with_company(company).try_loading("eg", company=company, install_demo=False)
        except Exception:
            _logger.exception("Failed to load Egypt chart for %s", company.name)
    ensure_ops(env)


def ensure_ops(env):
    """Runtime setup that can also be re-run after install."""
    eg = env.ref("base.eg")
    main = env["res.company"].search([("name", "=", "Home Blend")], limit=1) or env.ref("base.main_company")
    art = env["res.company"].search([("name", "=", "Art Casa")], limit=1)
    admin = env.ref("base.user_admin")

    def step(name, func):
        try:
            with env.cr.savepoint():
                func()
        except Exception:
            _logger.exception("Ops step failed: %s", name)

    step("archive companies", lambda: _archive_demo_companies(env, main, art))
    step("egyptize", lambda: _egyptize_homeblend(env, main, eg))
    step("egp pricing", lambda: _ensure_egp_pricing(env, main, art))
    step("groups", lambda: _enable_feature_groups(env, admin))
    step("vat main", lambda: _ensure_eg_vat(env, main))
    if art:
        step("vat art", lambda: _ensure_eg_vat(env, art))
        step("warehouses", lambda: _ensure_artcasa_warehouses(env, art))
        step("admin companies", lambda: admin.write({"company_ids": [Command.link(art.id)]}))
    step("loyalty", lambda: _ensure_loyalty(env, main))
    step("coupon", lambda: _ensure_coupon(env, main))
    step("loyalty points", lambda: _ensure_loyalty_points(env, main))
    step("fixed coupon", lambda: _ensure_fixed_coupon(env, main))
    step("extra coupons", lambda: _ensure_extra_coupons(env, main))
    step("credit limits", lambda: _enable_credit_limits(env, main, art))
    step("master data", lambda: _ensure_master_data(env, main, art))
    step("taxes defaults", lambda: _apply_default_taxes(env, main, art))
    step("barcodes", lambda: _ensure_barcodes(env))
    if art:
        step("pricelist", lambda: _ensure_artcasa_pricelist(env, art))
    step("payment terms", lambda: _ensure_payment_terms(env, main, art))
    step("collection methods", lambda: _ensure_collection_methods(env, main, art))
    step("purchase approval", lambda: _ensure_purchase_approval(env, main, art))
    step("contract terms", lambda: _link_contract_payment_term(env, main, art))
    if art:
        step("orderpoints", lambda: _ensure_orderpoints(env, art))
        step("opening stock", lambda: _ensure_artcasa_opening_stock(env, art))
    if "website" in env:
        step("websites", lambda: _rename_websites(env, main))
    if "pos.config" in env:
        step("pos configs", lambda: _ensure_pos_configs(env, main, art))
    if art and "loyalty.program" in env:
        step("art loyalty", lambda: _ensure_loyalty(env, art))
        step("art loyalty points", lambda: _ensure_loyalty_points(env, art))
        step("art coupon", lambda: _ensure_artcasa_coupon(env, art))
    if "loyalty.program" in env and "pos_ok" in env["loyalty.program"]._fields:
        step("loyalty pos", lambda: env["loyalty.program"].search([("pos_ok", "=", False)]).write({"pos_ok": True}))
    _logger.info("HomeBlend operational setup completed")


def _archive_demo_companies(env, main, art):
    keep = (main | art).ids
    extras = env["res.company"].search([("id", "not in", keep), ("active", "=", True)])
    if extras:
        extras.write({"active": False})
        _logger.info("Archived extra companies: %s", extras.mapped("name"))


def _ensure_egp_pricing(env, main, art=None):
    """كل الأسعار والتعاملات بالجنيه المصري."""
    egp = env.ref("base.EGP")
    egp.sudo().write({
        "active": True,
        "symbol": "ج.م.",
        "position": "after",
        "currency_unit_label": "جنيه",
        "currency_subunit_label": "قرش",
    })
    companies = main
    if art:
        companies |= art
    Pricelist = env["product.pricelist"].sudo()
    Partner = env["res.partner"].sudo()
    for company in companies:
        if company.currency_id != egp:
            try:
                company.write({"currency_id": egp.id})
            except Exception:
                _logger.exception("Could not set %s currency to EGP", company.name)
        pricelists = Pricelist.search([("company_id", "=", company.id)])
        if not pricelists:
            pricelists = Pricelist.with_company(company).create({
                "name": "قائمة أسعار %s" % company.name,
                "company_id": company.id,
                "currency_id": egp.id,
            })
        else:
            pricelists.filtered(lambda p: p.currency_id != egp).write({"currency_id": egp.id})
        default_pl = pricelists.filtered(lambda p: "قائمة أسعار" in (p.name or ""))[:1] or pricelists[:1]
        if "property_product_pricelist" in Partner._fields:
            company.partner_id.with_company(company).property_product_pricelist = default_pl.id
            partners = Partner.search([
                "|",
                ("company_id", "=", company.id),
                "&",
                ("company_id", "=", False),
                ("id", "child_of", company.partner_id.id),
            ])
            for partner in partners:
                current = partner.with_company(company).property_product_pricelist
                if not current or current.currency_id != egp:
                    partner.with_company(company).property_product_pricelist = default_pl.id
        if "pos.config" in env:
            for config in env["pos.config"].search([("company_id", "=", company.id)]):
                if "pricelist_id" in config._fields and default_pl:
                    vals = {}
                    if config.pricelist_id != default_pl:
                        vals["pricelist_id"] = default_pl.id
                    if "available_pricelist_ids" in config._fields and default_pl.id not in config.available_pricelist_ids.ids:
                        vals["available_pricelist_ids"] = [Command.link(default_pl.id)]
                    if vals:
                        config.write(vals)
    if "sale.order" in env:
        drafts = env["sale.order"].sudo().search([
            ("company_id", "in", companies.ids),
            ("currency_id", "!=", egp.id),
            ("state", "in", ["draft", "sent"]),
        ])
        for order in drafts:
            pl = order.pricelist_id if order.pricelist_id.currency_id == egp else Pricelist.search([
                ("company_id", "=", order.company_id.id),
                ("currency_id", "=", egp.id),
            ], limit=1)
            vals = {"currency_id": egp.id}
            if pl:
                vals["pricelist_id"] = pl.id
            order.write(vals)


def _egyptize_homeblend(env, company, eg):
    try:
        if "hr.leave" in env:
            domain = [
                ("employee_company_id", "=", company.id),
                ("holiday_status_id.country_id", "!=", False),
                ("holiday_status_id.country_id", "!=", eg.id),
            ]
            env["hr.leave"].sudo().search(domain).unlink()
            env["hr.leave.allocation"].sudo().search(domain).unlink()
    except Exception:
        _logger.exception("Could not clear conflicting time-off records")
    try:
        company.write({
            "country_id": eg.id,
            "account_fiscal_country_id": eg.id,
            "currency_id": env.ref("base.EGP").id,
        })
    except Exception:
        _logger.exception("Could not set Home Blend country to Egypt")
        try:
            company.write({"account_fiscal_country_id": eg.id})
        except Exception:
            _logger.exception("Could not set Home Blend fiscal country")


def _enable_feature_groups(env, admin):
    xmlids = [
        "base.group_multi_company",
        "stock.group_production_lot",
        "stock.group_stock_multi_warehouses",
        "stock.group_stock_multi_locations",
        "product.group_product_pricelist",
        # مراكز التكلفة: بدونها تظهر القائمة ويفشل فتحها بخطأ وصول
        "analytic.group_analytic_accounting",
        "homeblend_base.group_homeblend_manager",
        "point_of_sale.group_pos_manager",
        "point_of_sale.group_pos_user",
    ]
    links = []
    for xid in xmlids:
        rec = env.ref(xid, raise_if_not_found=False)
        if rec:
            links.append(Command.link(rec.id))
    if links:
        admin.write({"group_ids": links})


def _ensure_eg_vat(env, company, tax_use="sale"):
    Tax = env["account.tax"].with_company(company)
    existing = Tax.search([
        ("company_id", "=", company.id),
        ("type_tax_use", "=", tax_use),
        ("amount", "=", 14.0),
        ("amount_type", "=", "percent"),
    ], limit=1)
    if existing:
        return existing
    TaxGroup = env["account.tax.group"].with_company(company)
    eg = env.ref("base.eg")
    group = TaxGroup.search([
        ("company_id", "=", company.id),
        ("country_id", "=", eg.id),
    ], limit=1)
    if not group:
        group = TaxGroup.create({
            "name": "ضريبة القيمة المضافة",
            "company_id": company.id,
            "country_id": eg.id,
        })
    label = "ضريبة القيمة المضافة 14%" if tax_use == "sale" else "ضريبة مشتريات 14%"
    return Tax.create({
        "name": label,
        "amount": 14.0,
        "amount_type": "percent",
        "type_tax_use": tax_use,
        "company_id": company.id,
        "country_id": eg.id,
        "tax_group_id": group.id,
        "invoice_label": "14%",
    })


def _ensure_artcasa_warehouses(env, art):
    Warehouse = env["stock.warehouse"].with_company(art)
    if not Warehouse.search([("company_id", "=", art.id)], limit=1):
        try:
            Warehouse.create({"name": "Art Casa Cairo", "code": "AC", "company_id": art.id})
        except Exception:
            _logger.exception("Could not create Art Casa main warehouse")
    if not Warehouse.search([("code", "=", "AC2"), ("company_id", "=", art.id)], limit=1):
        try:
            Warehouse.create({"name": "Art Casa Alexandria", "code": "AC2", "company_id": art.id})
        except Exception:
            _logger.exception("Could not create Art Casa second warehouse")


def _ensure_loyalty(env, company):
    if "loyalty.program" not in env:
        return
    Program = env["loyalty.program"].with_company(company)
    if Program.search([("name", "=", "كوبونات Home Blend"), ("company_id", "=", company.id)], limit=1):
        return
    try:
        program = Program.create({
            "name": "كوبونات Home Blend",
            "program_type": "coupons",
            "applies_on": "current",
            "trigger": "with_code",
            "company_id": company.id,
            "currency_id": company.currency_id.id,
            "portal_visible": True,
        })
        env["loyalty.reward"].create({
            "program_id": program.id,
            "reward_type": "discount",
            "discount": 10.0,
            "discount_mode": "percent",
            "discount_applicability": "order",
            "required_points": 1,
        })
        env["loyalty.rule"].create({
            "program_id": program.id,
            "minimum_qty": 1,
            "reward_point_amount": 1,
            "reward_point_mode": "order",
        })
    except Exception:
        _logger.exception("Could not create loyalty/coupon program")


def _ensure_coupon(env, company):
    if "loyalty.program" not in env or "loyalty.card" not in env:
        return
    program = env["loyalty.program"].search([
        ("name", "=", "كوبونات Home Blend"),
        ("company_id", "=", company.id),
    ], limit=1)
    if not program:
        return
    Card = env["loyalty.card"]
    if Card.search([("code", "=", "HB10")], limit=1):
        return
    Card.create({
        "program_id": program.id,
        "code": "HB10",
        "points": 1,
    })


def _ensure_loyalty_points(env, company):
    if "loyalty.program" not in env:
        return
    Program = env["loyalty.program"].with_company(company)
    if Program.search([("name", "=", "نقاط ولاء Home Blend"), ("company_id", "=", company.id)], limit=1):
        return
    Program.create({
        "name": "نقاط ولاء Home Blend",
        "program_type": "loyalty",
        "trigger": "auto",
        "applies_on": "both",
        "company_id": company.id,
        "currency_id": company.currency_id.id,
        "portal_visible": True,
        "date_to": date.today() + relativedelta(years=2),
        "rule_ids": [Command.create({
            "reward_point_amount": 1,
            "reward_point_mode": "money",
            "minimum_amount": 1,
        })],
        "reward_ids": [Command.create({
            "reward_type": "discount",
            "discount": 1,
            "discount_mode": "per_point",
            "discount_applicability": "order",
            "required_points": 100,
        })],
    })


def _ensure_fixed_coupon(env, company):
    if "loyalty.program" not in env:
        return
    Program = env["loyalty.program"].with_company(company)
    program = Program.search([("name", "=", "كوبون مبلغ ثابت Home Blend")], limit=1)
    if not program:
        program = Program.create({
            "name": "كوبون مبلغ ثابت Home Blend",
            "program_type": "coupons",
            "applies_on": "current",
            "trigger": "with_code",
            "company_id": company.id,
            "currency_id": company.currency_id.id,
            "limit_usage": True,
            "max_usage": 200,
            "date_from": date.today(),
            "date_to": date.today() + relativedelta(years=1),
            "portal_visible": True,
        })
        env["loyalty.reward"].create({
            "program_id": program.id,
            "reward_type": "discount",
            "discount": 50.0,
            "discount_mode": "per_order",
            "discount_applicability": "order",
            "required_points": 1,
        })
        env["loyalty.rule"].create({
            "program_id": program.id,
            "minimum_qty": 1,
            "reward_point_amount": 1,
            "reward_point_mode": "order",
        })
    Card = env["loyalty.card"]
    if not Card.search([("code", "=", "HB50")], limit=1):
        Card.create({
            "program_id": program.id,
            "code": "HB50",
            "points": 1,
            "expiration_date": date.today() + relativedelta(years=1),
        })


def _ensure_extra_coupons(env, company):
    if "loyalty.program" not in env:
        return

    def block(name, func):
        try:
            with env.cr.savepoint():
                func()
        except Exception:
            _logger.exception("extra coupon failed: %s", name)

    Program = env["loyalty.program"].with_company(company)
    Card = env["loyalty.card"]

    def category_coupon():
        categ = env["product.category"].search([], limit=1)
        if not categ or Program.search([("name", "=", "كوبون فئة منتجات Home Blend")], limit=1):
            return
        program = Program.create({
            "name": "كوبون فئة منتجات Home Blend",
            "program_type": "coupons",
            "applies_on": "current",
            "trigger": "with_code",
            "company_id": company.id,
            "currency_id": company.currency_id.id,
            "date_from": date.today(),
            "date_to": date.today() + relativedelta(years=1),
            "portal_visible": True,
        })
        env["loyalty.reward"].create({
            "program_id": program.id,
            "reward_type": "discount",
            "discount": 10.0,
            "discount_mode": "percent",
            "discount_applicability": "specific",
            "discount_product_category_id": categ.id,
            "required_points": 1,
        })
        env["loyalty.rule"].create({
            "program_id": program.id,
            "minimum_qty": 1,
            "reward_point_amount": 1,
            "reward_point_mode": "order",
            "product_category_id": categ.id,
        })
        Card.create({
            "program_id": program.id,
            "code": "HBCAT",
            "points": 1,
            "expiration_date": date.today() + relativedelta(years=1),
        })

    def one_time_coupon():
        if Program.search([("name", "=", "كوبون لمرة واحدة Home Blend")], limit=1):
            return
        program = Program.create({
            "name": "كوبون لمرة واحدة Home Blend",
            "program_type": "coupons",
            "applies_on": "current",
            "trigger": "with_code",
            "company_id": company.id,
            "currency_id": company.currency_id.id,
            "limit_usage": True,
            "max_usage": 1,
            "portal_visible": True,
        })
        env["loyalty.reward"].create({
            "program_id": program.id,
            "reward_type": "discount",
            "discount": 15.0,
            "discount_mode": "percent",
            "discount_applicability": "order",
            "required_points": 1,
        })
        env["loyalty.rule"].create({
            "program_id": program.id,
            "minimum_qty": 1,
            "reward_point_amount": 1,
            "reward_point_mode": "order",
        })
        Card.create({
            "program_id": program.id,
            "code": "HB1",
            "points": 1,
            "expiration_date": date.today() + relativedelta(months=6),
        })

    def group_coupon():
        Category = env["res.partner.category"]
        group = Category.search([("name", "=", "مجموعة كوبون Home Blend")], limit=1)
        if not group:
            group = Category.create({"name": "مجموعة كوبون Home Blend"})
        program = Program.search([("name", "=", "كوبون مجموعة عملاء Home Blend")], limit=1)
        if not program:
            program = Program.create({
                "name": "كوبون مجموعة عملاء Home Blend",
                "program_type": "coupons",
                "applies_on": "current",
                "trigger": "with_code",
                "company_id": company.id,
                "currency_id": company.currency_id.id,
                "portal_visible": True,
            })
            env["loyalty.reward"].create({
                "program_id": program.id,
                "reward_type": "discount",
                "discount": 8.0,
                "discount_mode": "percent",
                "discount_applicability": "order",
                "required_points": 1,
            })
            env["loyalty.rule"].create({
                "program_id": program.id,
                "minimum_qty": 1,
                "reward_point_amount": 1,
                "reward_point_mode": "order",
            })
            Card.create({
                "program_id": program.id,
                "code": "HBGROUP",
                "points": 1,
            })
        tenants = env["res.partner"].search([("is_tenant", "=", True), ("category_id", "in", group.ids)])
        for tenant in tenants:
            if program and not Card.search([("program_id", "=", program.id), ("partner_id", "=", tenant.id)], limit=1):
                Card.create({
                    "program_id": program.id,
                    "partner_id": tenant.id,
                    "points": 1,
                })

    block("category", category_coupon)
    block("one-time", one_time_coupon)
    block("group", group_coupon)


def _enable_credit_limits(env, main, art):
    companies = main | art if art else main
    for company in companies:
        if "account_use_credit_limit" in company._fields:
            company.account_use_credit_limit = True


def _apply_default_taxes(env, main, art):
    companies = main | art if art else main
    for company in companies:
        sale_tax = _ensure_eg_vat(env, company, "sale")
        purchase_tax = _ensure_eg_vat(env, company, "purchase")
        vals = {}
        if company.account_sale_tax_id != sale_tax:
            vals["account_sale_tax_id"] = sale_tax.id
        if company.account_purchase_tax_id != purchase_tax:
            vals["account_purchase_tax_id"] = purchase_tax.id
        if vals:
            company.write(vals)
        templates = env["product.template"].search([("company_id", "=", company.id)])
        for tmpl in templates:
            write_vals = {"taxes_id": [Command.set([sale_tax.id])]}
            if "supplier_taxes_id" in tmpl._fields:
                write_vals["supplier_taxes_id"] = [Command.set([purchase_tax.id])]
            tmpl.write(write_vals)
    commission = env["product.template"].search([("default_code", "=", "HB-COMMISSION")], limit=1)
    if commission and main:
        sale_tax = _ensure_eg_vat(env, main, "sale")
        commission.write({"taxes_id": [Command.set([sale_tax.id])]})


# مدة صفر تعني أن كل لوط يُولد منتهي الصلاحية، فيعترض أودو كل استلام
# بمعالج "منتجات منتهية". الصلاحية سنتان من الاستلام، وأودو يطرح بقية
# المدد من تاريخ الانتهاء: أفضل قبل بسنة، سحب قبل شهرين، تنبيه قبل شهر.
_EXPIRY_DEFAULTS = {
    "use_expiration_date": True,
    "expiration_time": 730,
    "use_time": 365,
    "removal_time": 60,
    "alert_time": 30,
}


def _ensure_barcodes(env):
    # الأرقام الثابتة للأصناف المرجعية، ورقم التحقق محسوب لا مكتوب يدوياً.
    mapping = {}
    for index, code in enumerate(("HB-SVC-01", "AC-FURN-01", "HB-COMMISSION", "HB-LATE-FEE"), start=1):
        base = "622100%06d" % index
        mapping[code] = base + _ean13_check_digit(base)
    Product = env["product.product"]
    for code, barcode in mapping.items():
        product = Product.search([("default_code", "=", code)], limit=1)
        if product and product.barcode != barcode:
            product.write({"barcode": barcode})
    _generate_goods_barcodes(env)


def _ean13_check_digit(twelve):
    """رقم التحقق في EAN-13: مجموع مرجّح 1 و 3 بالتناوب."""
    total = sum(int(digit) * (3 if index % 2 else 1) for index, digit in enumerate(twelve))
    return str((10 - total % 10) % 10)


def _generate_goods_barcodes(env):
    """باركود EAN-13 لكل سلعة مخزنية، وإتاحتها في نقطة البيع.

    بدون باركود لا يعمل الماسح لا في الجرد ولا في الفوترة، فالسلع الجديدة
    تحصل على رقم من البادئة المصرية 622 عند كل تشغيل.
    """
    Product = env["product.product"].sudo()
    goods = Product.search([("type", "=", "consu"), ("is_storable", "=", True)])
    missing = goods.filtered(lambda p: not p.barcode)
    if missing:
        used = set(Product.search([("barcode", "like", "622100%")]).mapped("barcode"))
        counter = 5
        for product in missing:
            while True:
                counter += 1
                base = "622100%06d" % counter
                candidate = base + _ean13_check_digit(base)
                if candidate not in used:
                    break
            used.add(candidate)
            product.write({"barcode": candidate})
    not_in_pos = goods.filtered(lambda p: not p.available_in_pos)
    if not_in_pos:
        not_in_pos.product_tmpl_id.write({"available_in_pos": True})


def _ensure_artcasa_pricelist(env, art):
    Pricelist = env["product.pricelist"].with_company(art)
    pl = Pricelist.search([("name", "=", "قائمة أسعار Art Casa"), ("company_id", "=", art.id)], limit=1)
    if not pl:
        pl = Pricelist.create({
            "name": "قائمة أسعار Art Casa",
            "company_id": art.id,
            "currency_id": art.currency_id.id,
        })
    product = env["product.product"].search([("default_code", "=", "AC-FURN-01")], limit=1)
    if product:
        tmpl = product.product_tmpl_id
        Item = env["product.pricelist.item"]
        if not Item.search([("pricelist_id", "=", pl.id), ("product_tmpl_id", "=", tmpl.id), ("min_quantity", "=", 0)], limit=1):
            Item.create({
                "pricelist_id": pl.id,
                "applied_on": "1_product",
                "product_tmpl_id": tmpl.id,
                "compute_price": "fixed",
                "fixed_price": product.lst_price or 3500.0,
            })
        if not Item.search([("pricelist_id", "=", pl.id), ("min_quantity", "=", 3)], limit=1):
            Item.create({
                "pricelist_id": pl.id,
                "applied_on": "1_product",
                "product_tmpl_id": tmpl.id,
                "compute_price": "percentage",
                "percent_price": 8.0,
                "min_quantity": 3,
            })
        if not Item.search([("pricelist_id", "=", pl.id), ("percent_price", "=", 12.0)], limit=1):
            Item.create({
                "pricelist_id": pl.id,
                "applied_on": "3_global",
                "compute_price": "percentage",
                "percent_price": 12.0,
                "date_start": datetime.combine(date.today(), datetime.min.time()),
                "date_end": datetime.combine(date.today() + relativedelta(months=3), datetime.max.time().replace(microsecond=0)),
            })
        if "property_product_pricelist" in art.partner_id._fields:
            art.partner_id.with_company(art).write({"property_product_pricelist": pl.id})
    alex = Pricelist.search([("name", "=", "قائمة أسعار الإسكندرية"), ("company_id", "=", art.id)], limit=1)
    if not alex:
        Pricelist.create({
            "name": "قائمة أسعار الإسكندرية",
            "company_id": art.id,
            "currency_id": art.currency_id.id,
        })


def _ensure_payment_terms(env, main, art):
    companies = main | art if art else main
    for company in companies:
        Term = env["account.payment.term"].with_company(company)
        if Term.search([("name", "=", "أقساط 3 أشهر"), ("company_id", "=", company.id)], limit=1):
            continue
        Term.create({
            "name": "أقساط 3 أشهر",
            "company_id": company.id,
            "note": "دفعة فورية ثم قسطان بعد 30 و 60 يوماً",
            "line_ids": [
                Command.create({"value": "percent", "value_amount": 33.33, "nb_days": 0, "delay_type": "days_after"}),
                Command.create({"value": "percent", "value_amount": 33.33, "nb_days": 30, "delay_type": "days_after"}),
                Command.create({"value": "percent", "value_amount": 33.34, "nb_days": 60, "delay_type": "days_after"}),
            ],
        })
        if not Term.search([("name", "=", "30 يوماً"), ("company_id", "=", company.id)], limit=1):
            Term.create({
                "name": "30 يوماً",
                "company_id": company.id,
                "line_ids": [
                    Command.create({"value": "percent", "value_amount": 100.0, "nb_days": 30, "delay_type": "days_after"}),
                ],
            })


def _ensure_purchase_approval(env, main, art):
    """اعتماد أمر الشراء بخطوتين فوق حد معيّن.

    أودو يمنح مدير الشراء اعتماداً تلقائياً، فالخطوة الثانية تُطلب فعلياً
    من موظفي المشتريات دون صلاحية المدير.
    """
    # الحد حقل نقدي، والكتابة على شركتين بعملتين مختلفتين ترفضها أودو.
    for company in (main | art) if art else main:
        company.write({
            "po_double_validation": "two_step",
            "po_double_validation_amount": 5000.0,
        })


def _ensure_collection_methods(env, main, art):
    """يومية نقدية وطرق قبض (تحويل بنكي / بطاقات / محافظ إلكترونية) لكل شركة.

    أودو Community لا ينشئ سوى "الدفع اليدوي"، فنضيف سطور طرق دفع مسمّاة على
    اليومية البنكية حتى يمكن تصنيف التحصيل حسب وسيلته في تقارير المدفوعات.
    """
    companies = main | art if art else main
    manual_in = env["account.payment.method"].search(
        [("code", "=", "manual"), ("payment_type", "=", "inbound")], limit=1
    )
    for company in companies:
        Journal = env["account.journal"].with_company(company)
        if not Journal.search([("company_id", "=", company.id), ("type", "=", "cash")], limit=1):
            Journal.create({
                "name": "الصندوق النقدي",
                "type": "cash",
                "code": "CSH",
                "company_id": company.id,
            })
        bank = Journal.search([("company_id", "=", company.id), ("type", "=", "bank")], limit=1)
        if not bank or not manual_in:
            continue
        Line = env["account.payment.method.line"].with_company(company)
        existing = set(bank.inbound_payment_method_line_ids.mapped("name"))
        for name in ("تحويل بنكي", "بطاقة دفع (مدى/فيزا)", "محفظة إلكترونية"):
            if name in existing:
                continue
            Line.create({
                "name": name,
                "payment_method_id": manual_in.id,
                "journal_id": bank.id,
            })


def _ensure_master_data(env, main, art):
    Partner = env["res.partner"]
    tenant = Partner.search([("is_tenant", "=", True), ("name", "=", "معرض النور")], limit=1)
    if not tenant:
        tenant = Partner.create({
            "name": "معرض النور",
            "is_company": True,
            "is_tenant": True,
            "company_id": main.id,
            "vat": "100-200-300",
        })
    Contract = env["homeblend.tenant.contract"]
    if not Contract.search([("tenant_id", "=", tenant.id), ("state", "=", "active")], limit=1):
        today = date.today()
        Contract.create({
            "tenant_id": tenant.id,
            "company_id": main.id,
            "date_start": today,
            "date_end": today + relativedelta(years=1),
            "commission_percent": 20.0,
            "commission_base": "before_tax",
            "state": "active",
        })
    Product = env["product.product"].with_company(main)
    if not Product.search([("default_code", "=", "HB-SVC-01")], limit=1):
        Product.create({
            "name": "خدمة تنفيذ طلب Home Blend",
            "default_code": "HB-SVC-01",
            "type": "service",
            "list_price": 500.0,
            "invoice_policy": "order",
            "sale_ok": True,
            "purchase_ok": False,
            "company_id": main.id,
        })
    if art:
        if not env["product.product"].with_company(art).search([("default_code", "=", "AC-FURN-01")], limit=1):
            tmpl_vals = {
                "name": "قطعة أثاث Art Casa",
                "default_code": "AC-FURN-01",
                "type": "consu",
                "list_price": 3500.0,
                "standard_price": 1800.0,
                "sale_ok": True,
                "purchase_ok": True,
                "company_id": art.id,
                "extra_cost_freight": 150.0,
                "extra_cost_shipping": 80.0,
            }
            if "is_storable" in env["product.template"]._fields:
                tmpl_vals["is_storable"] = True
            if "tracking" in env["product.template"]._fields:
                tmpl_vals["tracking"] = "lot"
            if "use_expiration_date" in env["product.template"]._fields:
                tmpl_vals.update(_EXPIRY_DEFAULTS)
            tmpl_vals["product_group"] = "أثاث"
            tmpl_vals["brand_name"] = "Art Casa"
            tmpl_vals["min_stock_qty"] = 2
            tmpl_vals["max_stock_qty"] = 20
            eg = env.ref("base.eg", raise_if_not_found=False)
            if eg:
                tmpl_vals["origin_country_id"] = eg.id
            categ = env["product.category"].with_company(art).search([("name", "=", "أثاث Art Casa")], limit=1)
            if not categ:
                parent = env.ref("product.product_category_all", raise_if_not_found=False)
                categ = env["product.category"].with_company(art).create({
                    "name": "أثاث Art Casa",
                    "parent_id": parent.id if parent else False,
                })
            tmpl_vals["categ_id"] = categ.id
            env["product.template"].with_company(art).create(tmpl_vals)
        else:
            existing = env["product.template"].search([("default_code", "=", "AC-FURN-01")], limit=1)
            updates = {}
            if existing and "use_expiration_date" in existing._fields and any(
                existing[field] != value for field, value in _EXPIRY_DEFAULTS.items()
            ):
                updates.update(_EXPIRY_DEFAULTS)
            if existing and not existing.product_group:
                updates["product_group"] = "أثاث"
            if existing and not existing.brand_name:
                updates["brand_name"] = "Art Casa"
            if existing and not existing.min_stock_qty:
                updates["min_stock_qty"] = 2
            if existing and not existing.max_stock_qty:
                updates["max_stock_qty"] = 20
            eg = env.ref("base.eg", raise_if_not_found=False)
            if existing and not existing.origin_country_id and eg:
                updates["origin_country_id"] = eg.id
            if existing and not existing.categ_id:
                categ = env["product.category"].with_company(art).search([("name", "=", "أثاث Art Casa")], limit=1)
                if not categ:
                    parent = env.ref("product.product_category_all", raise_if_not_found=False)
                    categ = env["product.category"].with_company(art).create({
                        "name": "أثاث Art Casa",
                        "parent_id": parent.id if parent else False,
                    })
                updates["categ_id"] = categ.id
            if existing and updates:
                existing.write(updates)


def _link_contract_payment_term(env, main, art=None):
    if "homeblend.tenant.contract" not in env:
        return
    companies = main | art if art else main
    for company in companies:
        term = env["account.payment.term"].search([
            ("name", "=", "أقساط 3 أشهر"),
            ("company_id", "=", company.id),
        ], limit=1)
        if not term:
            continue
        env["homeblend.tenant.contract"].search([
            ("company_id", "=", company.id),
            ("payment_term_id", "=", False),
        ]).write({"payment_term_id": term.id, "late_fee_percent": 2.0})


def _ensure_orderpoints(env, art):
    if "stock.warehouse.orderpoint" not in env:
        return
    product = env["product.product"].search([("default_code", "=", "AC-FURN-01")], limit=1)
    warehouse = env["stock.warehouse"].search([("company_id", "=", art.id)], limit=1)
    if not product or not warehouse:
        return
    Orderpoint = env["stock.warehouse.orderpoint"].with_company(art)
    if Orderpoint.search([("product_id", "=", product.id), ("warehouse_id", "=", warehouse.id)], limit=1):
        return
    Orderpoint.create({
        "product_id": product.id,
        "warehouse_id": warehouse.id,
        "product_min_qty": 2.0,
        "product_max_qty": 10.0,
        "company_id": art.id,
    })


def _ensure_artcasa_opening_stock(env, art):
    product = env["product.product"].search([("default_code", "=", "AC-FURN-01")], limit=1)
    warehouse = env["stock.warehouse"].search([("company_id", "=", art.id), ("code", "=", "AC")], limit=1)
    if not product or not warehouse:
        return
    qty = product.with_context(warehouse_id=warehouse.id).qty_available
    if qty >= 5:
        return
    lot_vals = {
        "name": "AC-OPEN-01",
        "product_id": product.id,
        "company_id": art.id,
    }
    Lot = env["stock.lot"].with_company(art)
    lot = Lot.search([("name", "=", "AC-OPEN-01"), ("product_id", "=", product.id)], limit=1)
    if not lot and product.tracking in ("lot", "serial"):
        if "expiration_date" in Lot._fields:
            lot_vals["expiration_date"] = datetime.now() + relativedelta(years=1)
        lot = Lot.create(lot_vals)
    Quant = env["stock.quant"].with_company(art).with_context(inventory_mode=True)
    vals = {
        "product_id": product.id,
        "location_id": warehouse.lot_stock_id.id,
        "inventory_quantity": 10.0,
    }
    if lot:
        vals["lot_id"] = lot.id
    quant = Quant.search([
        ("product_id", "=", product.id),
        ("location_id", "=", warehouse.lot_stock_id.id),
        ("lot_id", "=", lot.id if lot else False),
    ], limit=1)
    if quant:
        quant.inventory_quantity = 10.0
    else:
        quant = Quant.create(vals)
    quant.action_apply_inventory()


def _rename_websites(env, main):
    if "website" not in env:
        return
    websites = env["website"].search([("company_id", "=", main.id)])
    if websites:
        websites[:1].write({"name": "Home Blend"})


def _ensure_pos_configs(env, main, art):
    if "pos.config" not in env:
        return
    PosConfig = env["pos.config"].sudo()
    for company in filter(None, [main, art]):
        if PosConfig.search([("company_id", "=", company.id)], limit=1):
            continue
        PosConfig.with_company(company).create({
            "name": "%s POS" % company.name,
            "company_id": company.id,
        })
    if art:
        _ensure_artcasa_contract(env, art)
    _ensure_pos_invoice_followup(env, main, art)


def _ensure_pos_invoice_followup(env, main, art):
    """كل جلسة POS تصدر فاتورة عميل يمكن متابعتها، مع وسيلة أقساط من العقد."""
    if "pos.config" not in env:
        return
    PosConfig = env["pos.config"].sudo()
    Method = env["pos.payment.method"].sudo()
    Journal = env["account.journal"]
    for config in PosConfig.search([]):
        company = config.company_id
        if not config.invoice_journal_id:
            sale_journal = Journal.search([
                ("type", "=", "sale"),
                ("company_id", "=", company.id),
            ], limit=1)
            if sale_journal:
                config.invoice_journal_id = sale_journal.id
        method = Method.search([
            ("company_id", "=", company.id),
            ("name", "=", "أقساط / آجل"),
        ], limit=1)
        if not method:
            method = Method.with_company(company).create({
                "name": "أقساط / آجل",
                "company_id": company.id,
                "split_transactions": True,
            })
        if method.id not in config.payment_method_ids.ids:
            config.write({"payment_method_ids": [Command.link(method.id)]})


def _ensure_artcasa_contract(env, art):
    if "homeblend.tenant.contract" not in env:
        return
    Partner = env["res.partner"]
    dealer = Partner.search([("is_tenant", "=", True), ("name", "=", "وكيل Art Casa")], limit=1)
    if not dealer:
        dealer = Partner.create({
            "name": "وكيل Art Casa",
            "is_company": True,
            "is_tenant": True,
            "company_id": art.id,
        })
    Contract = env["homeblend.tenant.contract"]
    if Contract.search([("tenant_id", "=", dealer.id), ("company_id", "=", art.id), ("state", "=", "active")], limit=1):
        return
    today = date.today()
    Contract.create({
        "tenant_id": dealer.id,
        "company_id": art.id,
        "date_start": today,
        "date_end": today + relativedelta(years=1),
        "commission_percent": 15.0,
        "commission_base": "before_tax",
        "state": "active",
    })


def _ensure_artcasa_coupon(env, art):
    if "loyalty.program" not in env or "loyalty.card" not in env:
        return
    program = env["loyalty.program"].search([
        ("name", "=", "كوبونات Home Blend"),
        ("company_id", "=", art.id),
    ], limit=1)
    if not program:
        return
    Card = env["loyalty.card"]
    if Card.search([("code", "=", "AC10")], limit=1):
        return
    Card.create({
        "program_id": program.id,
        "code": "AC10",
        "points": 1,
    })
