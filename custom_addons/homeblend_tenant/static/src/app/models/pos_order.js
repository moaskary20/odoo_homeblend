import { patch } from "@web/core/utils/patch";
import { PosOrder } from "@point_of_sale/app/models/pos_order";

patch(PosOrder.prototype, {
    setup(vals) {
        super.setup(vals);
        if (this.partner_id || this.tenant_contract_id) {
            this.to_invoice = true;
        }
        this.paper_invoice = vals.paper_invoice || this.paper_invoice || false;
        this.paper_invoice_filename = vals.paper_invoice_filename || this.paper_invoice_filename || "";
    },
    setPartner(partner) {
        super.setPartner(partner);
        if (partner) {
            this.setToInvoice(true);
        }
        this._homeblendApplyPartnerContract(partner);
    },
    setContract(contract) {
        this.assertEditable();
        this.tenant_contract_id = contract || false;
        this.tenant_id = contract?.tenant_id || false;
        if (contract) {
            this.setToInvoice(true);
            this.payment_term_id = contract.payment_term_id || false;
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
    setPaperInvoice(datas, filename) {
        this.paper_invoice = datas || false;
        this.paper_invoice_filename = filename || "";
    },
});
