import { reactive } from "@odoo/owl";
import { registry } from "@web/core/registry";

export const homeMenuService = {
    start() {
        const state = reactive({ displayed: false });
        return {
            state,
            get displayed() {
                return state.displayed;
            },
            open() {
                state.displayed = true;
            },
            close() {
                state.displayed = false;
            },
            toggle() {
                state.displayed = !state.displayed;
            },
        };
    },
};

registry.category("services").add("home_menu", homeMenuService);
