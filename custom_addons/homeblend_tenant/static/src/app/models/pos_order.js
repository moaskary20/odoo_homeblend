import { patch } from "@web/core/utils/patch";
import { PosOrder } from "@point_of_sale/app/models/pos_order";

patch(PosOrder.prototype, {
    setup(vals) {
        super.setup(vals);
        if (this.tenant_contract_id) {
            this.to_invoice = true;
        }
    },
    setPartner(partner) {
        super.setPartner(partner);
        this._homeblendApplyPartnerContract(partner);
    },
    setContract(contract) {
        this.assertEditable();
        this.tenant_contract_id = contract || false;
        this.tenant_id = contract?.tenant_id || false;
        if (contract) {
            this.setToInvoice(true);
            if (contract.tenant_id && this.getPartner()?.id !== contract.tenant_id.id) {
                this.partner_id = contract.tenant_id;
                this.updatePricelistAndFiscalPosition(contract.tenant_id);
            }
        }
    },
    _homeblendApplyPartnerContract(partner) {
        if (!partner?.is_tenant) {
            return;
        }
        this.tenant_id = partner;
        const companyId = this.company?.id || this.config?.company_id?.id;
        const contracts = this.models["homeblend.tenant.contract"]?.getAll?.() || [];
        const match = contracts.find(
            (contract) =>
                contract.tenant_id?.id === partner.id &&
                (!companyId || contract.company_id?.id === companyId || contract.company_id === companyId)
        );
        if (match) {
            this.setContract(match);
        }
    },
});
