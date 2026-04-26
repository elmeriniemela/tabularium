/** @odoo-module **/

import { useService } from "@web/core/utils/hooks";
import { Layout } from "@web/search/layout";
import { useModelWithSampleData } from "@web/model/model";
import { standardViewProps } from "@web/views/standard_view_props";
import { useSetupAction } from "@web/search/action_hook";
import { SearchBar } from "@web/search/search_bar/search_bar";
import { useSearchBarToggler } from "@web/search/search_bar/search_bar_toggler";
import { CogMenu } from "@web/search/cog_menu/cog_menu";

import { Component, useRef } from "@odoo/owl";

export class ChartController extends Component {
    static template = "chart_widget.ChartView";
    static components = { Layout, SearchBar, CogMenu };
    static props = {
        ...standardViewProps,
        Model: Function,
        modelParams: Object,
        Renderer: Function,
    };

    setup() {
        this.model = useModelWithSampleData(this.props.Model, this.props.modelParams);
        this.actionService = useService("action");

        useSetupAction({
            rootRef: useRef("root"),
            getLocalState: () => {
                return { metaData: this.model.metaData };
            },
        });
        this.searchBarToggler = useSearchBarToggler();
    }

    openDomain(domain) {
        const context = { ...(this.model.searchParams?.context || this.props.context || {}) };
        for (const key of Object.keys(context)) {
            if (key === "group_by" || key.startsWith("search_default_")) {
                delete context[key];
            }
        }

        const viewIds = {};
        for (const [viewId, viewType] of this.env.config.views || []) {
            viewIds[viewType] = viewId;
        }

        this.actionService.doAction(
            {
                context,
                domain,
                name: this.model.metaData.title,
                res_model: this.model.metaData.resModel,
                search_view_id: this.env.config.views?.find((view) => view[1] === "search"),
                target: "current",
                type: "ir.actions.act_window",
                views: [
                    [viewIds.list || false, "list"],
                    [viewIds.form || false, "form"],
                ],
            },
            { viewType: "list" }
        );
    }
}
