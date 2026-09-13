import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import { SelectionPopup } from "@point_of_sale/app/components/popups/selection_popup/selection_popup";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";

patch(ControlButtons.prototype, {
    getContractList() {
        const current = this.currentOrder?.tenant_contract_id;
        const companyId = this.pos.company?.id || this.pos.config?.company_id?.id;
        const partner = this.currentOrder?.getPartner();
        const contracts = this.pos.models["homeblend.tenant.contract"]?.getAll?.() || [];
        const filtered = contracts.filter((contract) => {
            if (companyId && contract.company_id?.id && contract.company_id.id !== companyId) {
                return false;
            }
            return true;
        });
        const preferred = partner?.is_tenant
            ? filtered.filter((contract) => contract.tenant_id?.id === partner.id)
            : filtered;
        const list = (preferred.length ? preferred : filtered).map((contract) => ({
            id: contract.id,
            label: `${contract.name} — ${contract.tenant_id?.name || ""} (${contract.commission_percent || 0}%)`,
            isSelected: current && current.id === contract.id,
            item: contract,
        }));
        list.unshift({
            id: -1,
            label: _t("بدون عقد"),
            isSelected: !current,
            item: false,
        });
        return list;
    },
    async clickContract() {
        const selected = await makeAwaitable(this.dialog, SelectionPopup, {
            title: _t("اختر عقد البيع"),
            list: this.getContractList(),
        });
        if (selected === undefined) {
            return;
        }
        this.currentOrder.setContract(selected || false);
    },
});
