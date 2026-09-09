import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { useState } from "@odoo/owl";
import { NavBar } from "@web/webclient/navbar/navbar";

patch(NavBar.prototype, {
    setup() {
        super.setup(...arguments);
        this.homeMenuService = useService("home_menu");
        this.homeMenu = useState(this.homeMenuService.state);
    },
    onHomeMenuToggle(ev) {
        ev?.preventDefault?.();
        this.homeMenuService.toggle();
        this._closeAppMenuSidebar();
    },
});
