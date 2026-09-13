import { registry } from "@web/core/registry";
import { Base } from "@point_of_sale/app/models/related_models";

export class HomeblendTenantContract extends Base {
    static pythonModel = "homeblend.tenant.contract";
}

registry.category("pos_available_models").add(HomeblendTenantContract.pythonModel, HomeblendTenantContract);
