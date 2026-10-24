import { patch } from "@web/core/utils/patch";
import { useState } from "@odoo/owl";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";

patch(PaymentScreen.prototype, {
    setup() {
        super.setup(...arguments);
        this.hbReceived = useState({ text: "", editing: false, lineUuid: null });
    },
    get hbReceivedAmount() {
        const line = this.selectedPaymentLine;
        if (!line) {
            return "";
        }
        if (this.hbReceived.editing && this.hbReceived.lineUuid === line.uuid) {
            return this.hbReceived.text;
        }
        const amount = line.getAmount();
        return Number.isFinite(amount) ? String(amount) : "";
    },
    onReceivedFocus() {
        const line = this.selectedPaymentLine;
        if (!line) {
            return;
        }
        this.hbReceived.editing = true;
        this.hbReceived.lineUuid = line.uuid;
        this.hbReceived.text = String(line.getAmount() ?? "");
    },
    onReceivedBlur() {
        this.hbReceived.editing = false;
    },
    onReceivedInput(ev) {
        const line = this.selectedPaymentLine;
        if (!line || !this._hbCanEditPaymentLine(line)) {
            return;
        }
        let raw = (ev.target.value || "").replace(/,/g, ".").replace(/[^\d.]/g, "");
        const parts = raw.split(".");
        if (parts.length > 2) {
            raw = `${parts[0]}.${parts.slice(1).join("")}`;
        }
        this.hbReceived.editing = true;
        this.hbReceived.lineUuid = line.uuid;
        this.hbReceived.text = raw;
        const amount = raw === "" || raw === "." ? 0 : parseFloat(raw);
        if (Number.isNaN(amount)) {
            return;
        }
        line.setAmount(amount);
        this.numberBuffer.set(String(amount));
    },
    _hbCanEditPaymentLine(line) {
        const terminal = line.payment_method_id?.payment_terminal;
        if (!terminal) {
            return true;
        }
        return ["pending", "retry"].includes(line.getPaymentStatus());
    },
});
