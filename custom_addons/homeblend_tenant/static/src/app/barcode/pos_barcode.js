import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { onMounted } from "@odoo/owl";
import { PosOrder } from "@point_of_sale/app/models/pos_order";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";
import { TicketScreen } from "@point_of_sale/app/screens/ticket_screen/ticket_screen";

patch(PosOrder.prototype, {
    get hbReceiptBarcode() {
        const invoiceName = this.account_move?.name;
        if (invoiceName && invoiceName !== "/") {
            return invoiceName;
        }
        return this.pos_reference || "";
    },
    get hbReceiptBarcodeUrl() {
        if (!this.hbReceiptBarcode) {
            return "";
        }
        const value = encodeURIComponent(this.hbReceiptBarcode);
        return `/report/barcode/?barcode_type=Code128&value=${value}&width=400&height=70&quiet=0`;
    },
});

patch(PosStore.prototype, {
    async homeblendFindRefund(code) {
        const raw = (code || "").trim();
        if (!raw) {
            return false;
        }
        return await this.data.orm.call("pos.order", "hb_find_refund_source", [raw]);
    },
    async homeblendLoadInvoiceRefund(code) {
        const info = await this.homeblendFindRefund(code);
        if (!info) {
            return false;
        }
        if (info.pos_uuid) {
            await this.data.loadServerOrders([["uuid", "=", info.pos_uuid]]);
            const order = this.models["pos.order"].find((item) => item.uuid === info.pos_uuid);
            if (!order) {
                return false;
            }
            this.homeblendRefundOrderUuid = order.uuid;
            this.navigate("TicketScreen");
            this.notification.add(
                _t("الفاتورة %s جاهزة للاسترجاع. راجع الكميات ثم اضغط استرجاع.", info.invoice_name),
                { type: "success" }
            );
            return true;
        }
        if (!info.lines?.length) {
            return false;
        }
        const order = this.addNewOrder();
        order.setToInvoice(true);
        if (info.partner_id) {
            let partner = this.models["res.partner"].get(info.partner_id);
            if (!partner) {
                const rows = await this.data.searchRead("res.partner", [["id", "=", info.partner_id]]);
                partner = rows?.[0];
            }
            if (partner) {
                order.setPartner(partner);
            }
        }
        for (const line of info.lines) {
            await this.loadNewProducts([["product_variant_ids", "in", [line.product_id]]]);
            const product = this.models["product.product"].get(line.product_id);
            if (!product) {
                continue;
            }
            await this.addLineToOrder(
                {
                    product_id: product,
                    product_tmpl_id: product.product_tmpl_id,
                    qty: -Math.abs(line.qty || 0),
                    price_unit: line.price_unit,
                    discount: line.discount || 0,
                },
                order,
                { force: true },
                false
            );
        }
        this.selectedOrderUuid = order.uuid;
        this.navigate("ProductScreen", { orderUuid: order.uuid });
        this.notification.add(
            _t("تم تحميل استرجاع الفاتورة %s. أتمم الدفع لإصدار إشعار دائن.", info.invoice_name),
            { type: "success" }
        );
        return true;
    },
});

patch(ProductScreen.prototype, {
    async _barcodeProductAction(code) {
        const raw = (code?.base_code || code?.code || "").trim();
        if (raw && (await this.pos.homeblendLoadInvoiceRefund(raw))) {
            this.sound.play("beep");
            this.pos.scanning = false;
            return;
        }
        if (raw) {
            await this.pos.loadNewProducts([["default_code", "=", raw]]);
            const product = this.pos.models["product.product"].find((item) => item.default_code === raw);
            if (product?.barcode && product.barcode !== code.base_code) {
                return super._barcodeProductAction({ ...code, base_code: product.barcode });
            }
            if (product && !this.pos.models["product.product"].getBy("barcode", code.base_code)) {
                this.sound.play("beep");
                await this.pos.addLineToCurrentOrder(
                    { product_id: product, product_tmpl_id: product.product_tmpl_id },
                    { code },
                    product.needToConfigure()
                );
                this.numberBuffer.reset();
                return;
            }
        }
        return super._barcodeProductAction(code);
    },
});

patch(TicketScreen.prototype, {
    setup() {
        super.setup(...arguments);
        onMounted(() => this._homeblendApplyScannedRefund());
    },
    _homeblendApplyScannedRefund() {
        const uuid = this.pos.homeblendRefundOrderUuid;
        if (!uuid) {
            return;
        }
        this.pos.homeblendRefundOrderUuid = null;
        const order = this.pos.models["pos.order"].find((item) => item.uuid === uuid);
        if (!order) {
            return;
        }
        this.state.filter = "SYNCED";
        this.setSelectedOrder(order);
        for (const line of order.getOrderlines?.() || order.lines || []) {
            const refundable = (line.qty || 0) - (line.refundedQty || 0);
            if (refundable <= 0) {
                continue;
            }
            const detail = this.getToRefundDetail(line);
            detail.qty = refundable;
        }
        const firstLine = order.getOrderlines?.()?.[0];
        if (firstLine) {
            this.state.selectedOrderlineIds[order.id] = firstLine.id;
        }
    },
    async onClickScanOrder(qrcode) {
        const text = (qrcode || "").trim();
        if (text && !text.includes("order_uuid")) {
            const opened = await this.pos.homeblendLoadInvoiceRefund(text);
            if (opened) {
                this.pos.scanning = false;
                this._homeblendApplyScannedRefund();
                return;
            }
        }
        return super.onClickScanOrder(...arguments);
    },
});
