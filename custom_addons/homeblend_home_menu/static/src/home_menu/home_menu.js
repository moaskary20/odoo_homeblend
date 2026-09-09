import { Component, useState, useExternalListener } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { getAppIcon } from "./app_icons";

export class HomeMenu extends Component {
    static template = "homeblend_home_menu.HomeMenu";
    static props = {};

    setup() {
        this.menuService = useService("menu");
        this.homeMenuService = useService("home_menu");
        this.state = useState({ query: "" });
        useExternalListener(window, "keydown", this.onWindowKeydown.bind(this));
    }

    get apps() {
        const query = this.state.query.trim().toLowerCase();
        return this.menuService.getApps().filter((app) => {
            if (!query) {
                return true;
            }
            return (app.name || "").toLowerCase().includes(query);
        });
    }

    iconFor(app) {
        return getAppIcon(app);
    }

    getAppHref(app) {
        return `/odoo/${app.actionPath || "action-" + app.actionID}`;
    }

    async onAppClick(app) {
        this.homeMenuService.close();
        await this.menuService.selectMenu(app);
    }

    onWindowKeydown(ev) {
        if (ev.target && ["INPUT", "TEXTAREA"].includes(ev.target.tagName)) {
            return;
        }
        if (ev.key === "Escape" && this.menuService.getCurrentApp()) {
            this.homeMenuService.close();
            return;
        }
        if (ev.key === "Backspace") {
            this.state.query = this.state.query.slice(0, -1);
            return;
        }
        if (ev.key.length === 1 && !ev.ctrlKey && !ev.metaKey && !ev.altKey) {
            this.state.query += ev.key;
        }
    }
}
