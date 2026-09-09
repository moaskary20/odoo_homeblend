import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { useState } from "@odoo/owl";
import { WebClient } from "@web/webclient/webclient";
import { HomeMenu } from "../home_menu/home_menu";

WebClient.components = {
    ...WebClient.components,
    HomeMenu,
};

patch(WebClient.prototype, {
    setup() {
        super.setup(...arguments);
        this.homeMenuService = useService("home_menu");
        this.homeMenu = useState(this.homeMenuService.state);
    },
    _loadDefaultApp() {
        this.homeMenuService.open();
    },
});
