/** @odoo-module */

import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { ListController } from "@web/views/list/list_controller";

export class PositionsList extends ListController {
    async fetchAndUpdateData() {
        await this.model.root.model.orm.call("investment.position", "web_refresh_prices", [this.props.domain]);
        await this.model.load({ ...this.model.config});
    }
}

export const positionsListView = {
    ...listView,
    Controller: PositionsList,
}

registry.category("views").add("positions_list", positionsListView);
