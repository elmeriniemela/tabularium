/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { ChartArchParser } from "./chart_arch_parser";
import { ChartModel } from "./chart_model";
import { ChartController } from "./chart_controller";
import { ChartRenderer } from "./chart_renderer";

const viewRegistry = registry.category("views");

export const chartView = {
    type: "chart",
    Controller: ChartController,
    Renderer: ChartRenderer,
    Model: ChartModel,
    ArchParser: ChartArchParser,
    searchMenuTypes: ["filter", "groupBy", "favorite"],

    props: (genericProps, view) => {
        let modelParams;
        if (genericProps.state) {
            modelParams = genericProps.state.metaData;
        } else {
            const { arch, fields, resModel } = genericProps;
            const parser = new view.ArchParser();
            const archInfo = parser.parse(arch, fields);
            modelParams = {
                fields,
                resModel,
                timeField: archInfo.timeField,
                seriesFields: archInfo.seriesFields,
                title: archInfo.title || _t("Chart"),
            };
        }

        return {
            ...genericProps,
            modelParams,
            Model: view.Model,
            Renderer: view.Renderer,
        };
    },
};

viewRegistry.add("chart", chartView);
