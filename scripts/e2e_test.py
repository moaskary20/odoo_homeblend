#!/usr/bin/env python3
"""End-to-end XML-RPC checks for HomeBlend / Art Casa custom modules."""
import ssl
import sys
import xmlrpc.client
from datetime import date, datetime, timedelta

URL = "http://127.0.0.1:8069"
DB = "homeblend"
USER = "admin"
PASSWORD = "admin"


def connect():
    common = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/common", allow_none=True)
    uid = common.authenticate(DB, USER, PASSWORD, {})
    if not uid:
        raise SystemExit("Authentication failed")
    models = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/object", allow_none=True)
    return uid, models


def execute(models, uid, model, method, *args, **kwargs):
    try:
        return models.execute_kw(DB, uid, PASSWORD, model, method, list(args), kwargs or {})
    except xmlrpc.client.Fault as exc:
        if "cannot marshal None" in str(exc):
            return True
        raise


def invoice_sale_order(models, uid, so_id, extra_context=None):
    ctx = {"active_model": "sale.order", "active_ids": [so_id], "active_id": so_id}
    if extra_context:
        ctx.update(extra_context)
    wiz = execute(
        models, uid, "sale.advance.payment.inv", "create",
        {"advance_payment_method": "delivered", "sale_order_ids": [(6, 0, [so_id])]},
        context=ctx,
    )
    execute(models, uid, "sale.advance.payment.inv", "create_invoices", [wiz], context=ctx)
    so = execute(models, uid, "sale.order", "read", [so_id], fields=["invoice_ids"])[0]
    return so["invoice_ids"]


def main():
    uid, models = connect()
    errors = []

    def check(name, cond, detail=""):
        if cond:
            print(f"OK  {name}")
        else:
            print(f"FAIL {name} {detail}")
            errors.append(name)

    companies = execute(models, uid, "res.company", "search_read", [], fields=["name"])
    names = {c["name"] for c in companies}
    check("company Home Blend", any("Home Blend" in n for n in names), names)
    check("company Art Casa", any("Art Casa" in n for n in names), names)
    hb = next(c for c in companies if "Home Blend" in c["name"] or c["name"] == "Home Blend")
    art = next(c for c in companies if "Art Casa" in c["name"])

    # --- Home Blend tenant commission flow ---
    tenant_id = execute(
        models, uid, "res.partner", "create",
        {
            "name": "مستأجر اختبار HomeBlend",
            "is_company": True,
            "is_tenant": True,
            "company_id": hb["id"],
        },
    )
    customer_id = execute(
        models, uid, "res.partner", "create",
        {"name": "عميل المستأجر", "is_company": True, "company_id": hb["id"]},
    )
    today = date.today()
    contract_id = execute(
        models, uid, "homeblend.tenant.contract", "create",
        {
            "tenant_id": tenant_id,
            "company_id": hb["id"],
            "date_start": str(today - timedelta(days=1)),
            "date_end": str(today + timedelta(days=365)),
            "commission_percent": 20.0,
            "commission_base": "before_tax",
            "state": "draft",
        },
    )
    execute(models, uid, "homeblend.tenant.contract", "action_activate", [contract_id])
    product_id = execute(
        models, uid, "product.product", "create",
        {
            "name": "خدمة اختبار مستأجر",
            "type": "service",
            "list_price": 1000.0,
            "invoice_policy": "order",
            "sale_ok": True,
            "taxes_id": [(6, 0, [])],
        },
    )
    so_id = execute(
        models, uid, "sale.order", "create",
        {
            "partner_id": customer_id,
            "tenant_id": tenant_id,
            "company_id": hb["id"],
            "order_line": [(0, 0, {"product_id": product_id, "product_uom_qty": 1, "price_unit": 1000.0, "tax_ids": [(6, 0, [])]})],
        },
    )
    execute(models, uid, "sale.order", "action_confirm", [so_id])
    so = execute(models, uid, "sale.order", "read", [so_id], fields=["state", "tenant_contract_id", "track_state"])[0]
    check("SO confirmed", so["state"] == "sale", so)
    check("SO has contract", bool(so["tenant_contract_id"]), so)
    tracks = execute(models, uid, "homeblend.order.track", "search", [["sale_order_id", "=", so_id]])
    check("order track created", bool(tracks), tracks)

    invoice_ids = invoice_sale_order(models, uid, so_id)
    if not invoice_ids:
        errors.append("create invoices")
        print("FAIL create invoices")
    else:
        execute(models, uid, "account.move", "action_post", invoice_ids)
        inv = execute(
            models, uid, "account.move", "read", invoice_ids,
            fields=["state", "amount_untaxed", "commission_invoice_id", "tenant_id", "is_commission_invoice"],
        )[0]
        check("sale invoice posted", inv["state"] == "posted", inv)
        check("commission invoice linked", bool(inv["commission_invoice_id"]), inv)
        if inv["commission_invoice_id"]:
            comm = execute(
                models, uid, "account.move", "read", [inv["commission_invoice_id"][0]],
                fields=["is_commission_invoice", "commission_amount", "amount_untaxed", "partner_id"],
            )[0]
            check("commission flag", comm["is_commission_invoice"], comm)
            check("commission amount 20%", abs(comm["commission_amount"] - 200.0) < 0.05 or abs(comm["amount_untaxed"] - 200.0) < 0.05, comm)

    # --- Art Casa split invoice ---
    art_customer = execute(
        models, uid, "res.partner", "create",
        {"name": "عميل Art Casa", "is_company": True, "company_id": art["id"]},
    )
    project_partner = execute(
        models, uid, "res.partner", "create",
        {"name": "شريك مشروع Art Casa", "is_company": True, "company_id": art["id"]},
    )
    project_id = execute(
        models, uid, "project.project", "create",
        {
            "name": "مشروع تقسيم فاتورة",
            "company_id": art["id"],
            "partner_id": art_customer,
            "allow_billable": True,
            "artcasa_split_invoicing": True,
            "customer_share_percent": 60.0,
            "project_share_percent": 40.0,
            "bill_partner_id": project_partner,
        },
    )
    art_product = execute(
        models, uid, "product.product", "create",
        {
            "name": "خدمة مشروع Art Casa",
            "type": "service",
            "list_price": 1000.0,
            "invoice_policy": "order",
            "sale_ok": True,
            "company_id": art["id"],
            "taxes_id": [(6, 0, [])],
        },
    )
    # extra costs are on template; write via product template if needed
    tmpl = execute(models, uid, "product.product", "read", [art_product], fields=["product_tmpl_id"])[0]
    execute(
        models, uid, "product.template", "write",
        [tmpl["product_tmpl_id"][0]],
        {"extra_cost_freight": 50.0},
    )
    art_so = execute(
        models, uid, "sale.order", "create",
        {
            "partner_id": art_customer,
            "company_id": art["id"],
            "project_id": project_id,
            "order_line": [(0, 0, {"product_id": art_product, "product_uom_qty": 1, "price_unit": 1000.0, "tax_ids": [(6, 0, [])]})],
        },
        context={"allowed_company_ids": [art["id"], hb["id"]]},
    )
    execute(
        models, uid, "sale.order", "action_confirm", [art_so],
        context={"allowed_company_ids": [art["id"], hb["id"]]},
    )
    art_so_data = execute(
        models, uid, "sale.order", "read", [art_so],
        fields=["project_id", "state", "company_id"],
        context={"allowed_company_ids": [art["id"], hb["id"]]},
    )[0]
    check("Art Casa SO has project", bool(art_so_data.get("project_id")), art_so_data)
    art_invoices = invoice_sale_order(
        models, uid, art_so, extra_context={"allowed_company_ids": [art["id"], hb["id"]]}
    )
    extra = execute(
        models, uid, "account.move", "search",
        [["artcasa_split_source_id", "in", art_invoices or [0]]],
        context={"allowed_company_ids": [art["id"], hb["id"]]},
    )
    all_inv = list(dict.fromkeys(list(art_invoices or []) + list(extra or [])))
    check("Art Casa two invoices", len(all_inv) == 2, {"so": art_invoices, "extra": extra, "project": art_so_data})
    if all_inv:
        moves = execute(
            models, uid, "account.move", "read", all_inv,
            fields=["artcasa_split_role", "amount_untaxed", "partner_id"],
            context={"allowed_company_ids": [art["id"], hb["id"]]},
        )
        roles = {m["artcasa_split_role"] for m in moves}
        check("split roles", roles == {"customer", "project"}, roles)
        amounts = {m["artcasa_split_role"]: m["amount_untaxed"] for m in moves}
        if "customer" in amounts:
            check("customer share 60%", abs(amounts["customer"] - 600.0) < 1.0, amounts)
        if "project" in amounts:
            check("project share 40%", abs(amounts["project"] - 400.0) < 1.0, amounts)

    # payroll
    emp = execute(
        models, uid, "hr.employee", "create",
        {"name": "موظف اختبار", "company_id": hb["id"]},
    )
    slip = execute(
        models, uid, "homeblend.payslip", "create",
        {
            "employee_id": emp,
            "company_id": hb["id"],
            "wage": 10000.0,
            "insurance_base": 10000.0,
        },
    )
    slip_data = execute(models, uid, "homeblend.payslip", "read", [slip], fields=["net", "insurance_employee", "tax_amount"])[0]
    check("payslip net computed", slip_data["net"] > 0, slip_data)
    execute(models, uid, "homeblend.payslip", "action_confirm", [slip])
    slip_state = execute(models, uid, "homeblend.payslip", "read", [slip], fields=["state"])[0]
    check("payslip confirmed", slip_state["state"] == "confirmed", slip_state)

    # documents
    doc = execute(
        models, uid, "homeblend.document", "create",
        {"name": "عقد اختبار", "datas": "dGVzdA==", "datas_fname": "test.txt", "document_type": "contract"},
    )
    execute(models, uid, "homeblend.document", "action_sign", [doc])
    doc_data = execute(models, uid, "homeblend.document", "read", [doc], fields=["sign_state"])[0]
    check("document signed", doc_data["sign_state"] == "signed", doc_data)

    # --- default 14% tax, barcode, coupon, pricelist, payment terms ---
    sale_taxes = execute(
        models, uid, "account.tax", "search_read",
        [["company_id", "=", hb["id"]], ["type_tax_use", "=", "sale"], ["amount", "=", 14.0]],
        fields=["name", "amount"],
    )
    check("VAT 14% Home Blend", bool(sale_taxes), sale_taxes)
    hb_svc = execute(
        models, uid, "product.product", "search_read",
        [["default_code", "=", "HB-SVC-01"]],
        fields=["barcode", "taxes_id"],
    )
    check("HB service barcode", bool(hb_svc and hb_svc[0].get("barcode")), hb_svc)
    ac_prod = execute(
        models, uid, "product.product", "search_read",
        [["default_code", "=", "AC-FURN-01"]],
        fields=["barcode"],
        context={"allowed_company_ids": [art["id"], hb["id"]]},
    )
    check("Art Casa barcode", bool(ac_prod and ac_prod[0].get("barcode")), ac_prod)
    ac_tmpl = execute(
        models, uid, "product.template", "search_read",
        [["default_code", "=", "AC-FURN-01"]],
        fields=["actual_cost", "qr_payload", "use_expiration_date", "product_group", "extra_cost_total", "net_profit_unit"],
        context={"allowed_company_ids": [art["id"], hb["id"]]},
    )
    check("Art Casa actual cost", bool(ac_tmpl and ac_tmpl[0].get("actual_cost", 0) > 0), ac_tmpl)
    check("Art Casa QR payload", bool(ac_tmpl and ac_tmpl[0].get("qr_payload")), ac_tmpl)
    check("Art Casa expiration tracking", bool(ac_tmpl and ac_tmpl[0].get("use_expiration_date")), ac_tmpl)
    alex_pl = execute(
        models, uid, "product.pricelist", "search_read",
        [["name", "=", "قائمة أسعار الإسكندرية"]],
        fields=["name"],
        context={"allowed_company_ids": [art["id"], hb["id"]]},
    )
    check("Art Casa Alexandria pricelist", bool(alex_pl), alex_pl)
    coupons = execute(models, uid, "loyalty.card", "search_read", [["code", "=", "HB10"]], fields=["code", "points"])
    check("coupon HB10", bool(coupons), coupons)
    pricelists = execute(
        models, uid, "product.pricelist", "search_read",
        [["name", "=", "قائمة أسعار Art Casa"]],
        fields=["name"],
        context={"allowed_company_ids": [art["id"], hb["id"]]},
    )
    check("Art Casa pricelist", bool(pricelists), pricelists)
    terms = execute(
        models, uid, "account.payment.term", "search_read",
        [["name", "=", "أقساط 3 أشهر"], ["company_id", "=", hb["id"]]],
        fields=["name"],
    )
    check("installment payment term", bool(terms), terms)

    # --- salesperson reservation consumed on confirm ---
    warehouses = execute(
        models, uid, "stock.warehouse", "search_read",
        [["company_id", "=", art["id"]]],
        fields=["name"],
        context={"allowed_company_ids": [art["id"], hb["id"]]},
    )
    check("Art Casa warehouse", bool(warehouses), warehouses)
    if warehouses and ac_prod:
        ctx_art = {"allowed_company_ids": [art["id"], hb["id"]]}
        wh = execute(
            models, uid, "stock.warehouse", "read", [warehouses[0]["id"]],
            fields=["lot_stock_id"], context=ctx_art,
        )[0]
        loc_id = wh["lot_stock_id"][0]
        inv_ctx = {**ctx_art, "inventory_mode": True}
        quants = execute(
            models, uid, "stock.quant", "search",
            [["product_id", "=", ac_prod[0]["id"]], ["location_id", "=", loc_id]],
            context=inv_ctx,
        )
        if quants:
            execute(models, uid, "stock.quant", "write", quants[:1], {"inventory_quantity": 10.0}, context=inv_ctx)
            qid = quants[0]
        else:
            qid = execute(
                models, uid, "stock.quant", "create",
                {"product_id": ac_prod[0]["id"], "location_id": loc_id, "inventory_quantity": 10.0},
                context=inv_ctx,
            )
        execute(models, uid, "stock.quant", "action_apply_inventory", [qid], context=inv_ctx)
        qty_before = execute(
            models, uid, "product.product", "read", [ac_prod[0]["id"]],
            fields=["qty_available", "free_qty"],
            context={**ctx_art, "warehouse_id": warehouses[0]["id"]},
        )[0]
        res_customer = execute(
            models, uid, "res.partner", "create",
            {"name": "عميل حجز مندوب", "is_company": True, "company_id": art["id"]},
        )
        now = datetime.utcnow()
        # release reservations left active by earlier runs, otherwise the sale order
        # would consume the oldest matching one instead of the one created below
        leftover = execute(
            models, uid, "artcasa.stock.reservation", "search",
            [
                ["product_id", "=", ac_prod[0]["id"]],
                ["warehouse_id", "=", warehouses[0]["id"]],
                ["state", "=", "reserved"],
            ],
            context=ctx_art,
        )
        if leftover:
            execute(models, uid, "artcasa.stock.reservation", "action_release", leftover, context=ctx_art)
        reservation = execute(
            models, uid, "artcasa.stock.reservation", "create",
            {
                "user_id": uid,
                "partner_id": res_customer,
                "product_id": ac_prod[0]["id"],
                "quantity": 1,
                "warehouse_id": warehouses[0]["id"],
                "date_start": (now - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S"),
                "date_end": (now + timedelta(days=5)).strftime("%Y-%m-%d %H:%M:%S"),
            },
            context=ctx_art,
        )
        execute(models, uid, "artcasa.stock.reservation", "action_reserve", [reservation], context=ctx_art)
        qty_after = execute(
            models, uid, "product.product", "read", [ac_prod[0]["id"]],
            fields=["qty_available", "free_qty"],
            context={**ctx_art, "warehouse_id": warehouses[0]["id"]},
        )[0]
        rsv_data = execute(
            models, uid, "artcasa.stock.reservation", "read", [reservation],
            fields=["state", "picking_id", "qty_on_hand"], context=ctx_art,
        )[0]
        check("reservation is virtual", rsv_data.get("state") == "reserved" and not rsv_data.get("picking_id"), rsv_data)
        check("reservation does not move stock", abs((qty_after.get("qty_available") or 0) - (qty_before.get("qty_available") or 0)) < 0.01, {"before": qty_before, "after": qty_after})
        check("reservation reduces free qty", (qty_after.get("free_qty") or 0) < (qty_before.get("free_qty") or 0) - 0.5, {"before": qty_before, "after": qty_after})
        overlap_failed = False
        try:
            overlap = execute(
                models, uid, "artcasa.stock.reservation", "create",
                {
                    "user_id": uid,
                    "partner_id": res_customer,
                    "product_id": ac_prod[0]["id"],
                    "quantity": 10,
                    "warehouse_id": warehouses[0]["id"],
                    "date_start": now.strftime("%Y-%m-%d %H:%M:%S"),
                    "date_end": (now + timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S"),
                },
                context=ctx_art,
            )
            execute(models, uid, "artcasa.stock.reservation", "action_reserve", [overlap], context=ctx_art)
        except xmlrpc.client.Fault:
            overlap_failed = True
        check("overlap reservation blocked", overlap_failed, "second salesman booked the same qty")
        expired = execute(
            models, uid, "artcasa.stock.reservation", "create",
            {
                "user_id": uid,
                "partner_id": res_customer,
                "product_id": ac_prod[0]["id"],
                "quantity": 1,
                "warehouse_id": warehouses[0]["id"],
                "date_start": (now - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S"),
                "date_end": (now - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S"),
            },
            context=ctx_art,
        )
        execute(models, uid, "artcasa.stock.reservation", "action_reserve", [expired], context=ctx_art)
        execute(models, uid, "artcasa.stock.reservation", "action_release_expired", [], context=ctx_art)
        exp_state = execute(
            models, uid, "artcasa.stock.reservation", "read", [expired],
            fields=["state"], context=ctx_art,
        )[0]
        check("expired reservation auto-released", exp_state.get("state") == "released", exp_state)
        res_so = execute(
            models, uid, "sale.order", "create",
            {
                "partner_id": res_customer,
                "company_id": art["id"],
                "user_id": uid,
                "warehouse_id": warehouses[0]["id"],
                "order_line": [(0, 0, {"product_id": ac_prod[0]["id"], "product_uom_qty": 1, "price_unit": 3500.0, "tax_ids": [(6, 0, [])]})],
            },
            context=ctx_art,
        )
        execute(models, uid, "sale.order", "action_confirm", [res_so], context=ctx_art)
        res_state = execute(
            models, uid, "artcasa.stock.reservation", "read", [reservation],
            fields=["state", "sale_order_id"],
            context=ctx_art,
        )[0]
        check("reservation consumed", res_state["state"] == "consumed", res_state)
        check("reservation linked to SO", bool(res_state.get("sale_order_id")), res_state)

    # --- asset depreciation journal entry ---
    asset = execute(
        models, uid, "homeblend.asset", "create",
        {
            "name": "أصل اختبار إهلاك",
            "company_id": hb["id"],
            "purchase_value": 12000.0,
            "salvage_value": 0.0,
            "method_years": 5,
        },
    )
    execute(models, uid, "homeblend.asset", "action_start", [asset])
    try:
        execute(models, uid, "homeblend.asset", "action_post_depreciation", [asset])
        asset_data = execute(
            models, uid, "homeblend.asset", "read", [asset],
            fields=["state", "last_depreciation_date", "depreciation_move_ids", "annual_depreciation"],
        )[0]
        check("asset running", asset_data["state"] == "running", asset_data)
        check("asset depreciation posted", bool(asset_data.get("depreciation_move_ids")), asset_data)
    except Exception as exc:
        check("asset depreciation posted", False, str(exc))

    # --- late fee on overdue tenant invoice ---
    if invoice_ids:
        execute(models, uid, "homeblend.tenant.contract", "write", [contract_id], {"late_fee_percent": 5.0})
        execute(
            models, uid, "account.move", "write",
            invoice_ids[:1],
            {"invoice_date_due": str(today - timedelta(days=1))},
        )
        execute(models, uid, "account.move", "action_generate_late_fees", [])
        inv_fee = execute(models, uid, "account.move", "read", invoice_ids[:1], fields=["late_fee_invoice_id", "amount_residual"])[0]
        check("late fee invoice created", bool(inv_fee.get("late_fee_invoice_id")), inv_fee)

    if ac_prod:
        orderpoints = execute(
            models, uid, "stock.warehouse.orderpoint", "search",
            [["product_id", "=", ac_prod[0]["id"]]],
            context={"allowed_company_ids": [art["id"], hb["id"]]},
        )
        check("Art Casa reorder point", bool(orderpoints), orderpoints)

    loyalty_pts = execute(
        models, uid, "loyalty.program", "search_read",
        [["name", "=", "نقاط ولاء Home Blend"]],
        fields=["name", "program_type"],
    )
    check("loyalty points program", bool(loyalty_pts), loyalty_pts)
    hb50 = execute(models, uid, "loyalty.card", "search_read", [["code", "=", "HB50"]], fields=["code", "points"])
    check("fixed coupon HB50", bool(hb50), hb50)
    for code, label in (("HBCAT", "category coupon HBCAT"), ("HB1", "one-time coupon HB1"), ("HBGROUP", "group coupon HBGROUP")):
        card = execute(models, uid, "loyalty.card", "search_read", [["code", "=", code]], fields=["code", "points"])
        check(label, bool(card), card)
    kpi_fields = execute(
        models, uid, "res.partner", "read", [tenant_id],
        fields=["tenant_kpi_on_time", "tenant_kpi_satisfaction", "tenant_kpi_contract_ok", "tenant_last_deal_date", "tenant_activity_count"],
    )[0]
    check("tenant KPI extras", "tenant_kpi_on_time" in kpi_fields, kpi_fields)
    contracts = execute(
        models, uid, "homeblend.tenant.contract", "search_read",
        [["tenant_id", "=", tenant_id]],
        fields=["expiring_soon", "renewed_from_id", "state"],
        limit=1,
    )
    check("contract expiry fields", bool(contracts) and "expiring_soon" in contracts[0], contracts)
    if invoice_ids:
        qr = execute(models, uid, "account.move", "read", invoice_ids[:1], fields=["homeblend_qr_payload", "state"])[0]
        check("invoice QR payload", bool(qr.get("homeblend_qr_payload")), qr)
    complaint = execute(
        models, uid, "homeblend.complaint", "create",
        {"name": "شكوى اختبار", "partner_id": tenant_id},
    )
    kpi = execute(models, uid, "res.partner", "read", [tenant_id], fields=["tenant_kpi_complaints", "tenant_score"])[0]
    check("tenant complaint counted", kpi.get("tenant_kpi_complaints", 0) >= 1, kpi)

    SIGN_PNG = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )
    ctx_shared = {"allowed_company_ids": [art["id"], hb["id"]]}
    if ac_prod:
        warehouses = execute(
            models, uid, "stock.warehouse", "search_read",
            [["company_id", "=", art["id"]]],
            fields=["lot_stock_id"],
            context=ctx_shared,
        )
        # الصنف متتبع بالتشغيلات، فالجرد يتم بمسح ملصق التشغيلة لا ملصق الصنف.
        lot_name = "LOT-E2E-SCAN"
        lots = execute(
            models, uid, "stock.lot", "search_read",
            [["name", "=", lot_name], ["product_id", "=", ac_prod[0]["id"]]],
            fields=["id"], context=ctx_shared,
        )
        lot_id = lots[0]["id"] if lots else execute(
            models, uid, "stock.lot", "create",
            {"name": lot_name, "product_id": ac_prod[0]["id"], "company_id": art["id"]},
            context=ctx_shared,
        )
        if warehouses and lot_id:
            loc = warehouses[0]["lot_stock_id"][0]
            scan_wiz = execute(
                models, uid, "artcasa.barcode.inventory", "create",
                {"location_id": loc},
                context=ctx_shared,
            )
            execute(
                models, uid, "artcasa.barcode.inventory", "action_scan",
                [scan_wiz], barcode=lot_name, context=ctx_shared,
            )
            scan_data = execute(
                models, uid, "artcasa.barcode.inventory", "read",
                [scan_wiz], fields=["line_ids"], context=ctx_shared,
            )[0]
            scan_lines = execute(
                models, uid, "artcasa.barcode.inventory.line", "read",
                scan_data.get("line_ids") or [],
                fields=["qty_counted", "product_id", "lot_id"],
                context=ctx_shared,
            ) if scan_data.get("line_ids") else []
            check(
                "barcode inventory scan",
                bool(scan_lines)
                and scan_lines[0].get("qty_counted", 0) >= 1
                and (scan_lines[0].get("lot_id") or [None])[0] == lot_id,
                scan_lines,
            )
    proj = execute(
        models, uid, "project.project", "create",
        {
            "name": "مشروع توقيع اختبار",
            "company_id": art["id"],
            "partner_id": customer_id,
            "signature": SIGN_PNG,
            "customer_share_percent": 60.0,
            "project_share_percent": 40.0,
        },
        context=ctx_shared,
    )
    execute(models, uid, "project.project", "action_sign_contract", [proj], context=ctx_shared)
    proj_data = execute(
        models, uid, "project.project", "read", [proj],
        fields=["signed", "signed_date", "signature"],
        context=ctx_shared,
    )[0]
    check("project contract signed", bool(proj_data.get("signed") and proj_data.get("signature")), proj_data)
    fin = execute(
        models, uid, "homeblend.financial.report.wizard", "create",
        {
            "report_type": "balance",
            "company_id": hb["id"],
            "date_from": str(date(today.year, 1, 1)),
            "date_to": str(today),
        },
    )
    fin_data = execute(models, uid, "homeblend.financial.report.wizard", "get_report_data", [fin])
    check(
        "financial balance PDF data",
        isinstance(fin_data, dict) and bool(fin_data.get("sections")),
        fin_data if isinstance(fin_data, dict) else type(fin_data),
    )
    check(
        "balance sheet balances",
        isinstance(fin_data, dict) and abs(fin_data.get("difference", 1)) < 0.01,
        {k: fin_data.get(k) for k in ("assets_total", "liab_equity_total", "difference")}
        if isinstance(fin_data, dict) else type(fin_data),
    )
    pnl = execute(
        models, uid, "homeblend.financial.report.wizard", "create",
        {
            "report_type": "pnl",
            "company_id": hb["id"],
            "date_from": str(today.replace(month=1, day=1)),
            "date_to": str(today),
        },
    )
    pnl_data = execute(models, uid, "homeblend.financial.report.wizard", "get_report_data", [pnl])
    income_total = pnl_data["sections"][0]["total"] if isinstance(pnl_data, dict) else 0
    check(
        "pnl income sign positive",
        isinstance(pnl_data, dict) and income_total > 0,
        pnl_data if isinstance(pnl_data, dict) else type(pnl_data),
    )
    expense_acc = execute(
        models, uid, "account.account", "search",
        [["account_type", "=", "expense"]],
        limit=1,
        context={"allowed_company_ids": [hb["id"]]},
    )
    if expense_acc:
        budget = execute(
            models, uid, "homeblend.budget", "create",
            {
                "name": "ميزانية اختبار",
                "company_id": hb["id"],
                "date_from": str(date(today.year, 1, 1)),
                "date_to": str(today),
                "line_ids": [(0, 0, {"account_id": expense_acc[0], "planned_amount": 1000.0})],
            },
        )
        execute(models, uid, "homeblend.budget", "action_open", [budget])
        budget_data = execute(
            models, uid, "homeblend.budget", "read",
            [budget], fields=["state", "planned_total"],
        )[0]
        check(
            "budget approved",
            budget_data.get("state") == "open" and abs(budget_data.get("planned_total", 0) - 1000.0) < 0.01,
            budget_data,
        )
    else:
        check("budget approved", False, "no expense account")

    if errors:
        print("FAILED:", ", ".join(errors))
        sys.exit(1)
    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
