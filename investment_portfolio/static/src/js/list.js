/** @odoo-module */

import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { ListController } from "@web/views/list/list_controller";
import { useService } from "@web/core/utils/hooks";

import {
    Component,
    onMounted,
    onWillPatch,
    onWillRender,
    onWillStart,
    useEffect,
    useRef,
    useState,
    useSubEnv,
} from "@odoo/owl";


export class PositionsList extends ListController {

    setup() {
        super.setup();
        onMounted(async () => {
            await this.fetchAndUpdateData();
        });
    }

    // Method to fetch data from an API and update the list
    async fetchAndUpdateData() {
        try {
            // Example: Make an RPC call to a custom backend method
            await this.orm.call("investment.position", "web_refresh_prices", [this.props.domain]);
            await this.model.load({ ...this.model.config});
        } catch (error) {
            console.error("Failed to fetch data:", error);
        }
    }

}


export const positionsListView = {
    ...listView,
    Controller: PositionsList,
}

registry.category("views").add("positions_list", positionsListView);
