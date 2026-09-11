import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { useState } from "@odoo/owl";
import { localization } from "@web/core/l10n/localization";
import { WebClient } from "@web/webclient/webclient";
import { HomeMenu } from "../home_menu/home_menu";

function applyDocumentDirection() {
    const rtl = localization.direction === "rtl";
    const dir = rtl ? "rtl" : "ltr";
    document.documentElement.setAttribute("dir", dir);
    document.body.setAttribute("dir", dir);
    document.body.classList.toggle("o_rtl", rtl);
}

WebClient.components = {
    ...WebClient.components,
    HomeMenu,
};

patch(WebClient.prototype, {
    setup() {
        super.setup(...arguments);
        this.homeMenuService = useService("home_menu");
        this.homeMenu = useState(this.homeMenuService.state);
        applyDocumentDirection();
    },
    _loadDefaultApp() {
        this.homeMenuService.open();
    },
});
