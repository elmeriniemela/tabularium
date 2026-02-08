/** @odoo-module **/

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

        useSetupAction({
            rootRef: useRef("root"),
            getLocalState: () => {
                return { metaData: this.model.metaData };
            },
        });
        this.searchBarToggler = useSearchBarToggler();
    }
}
