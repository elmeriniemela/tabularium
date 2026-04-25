/** @odoo-module **/

import { visitXML } from "@web/core/utils/xml";

const SERIES_TYPES = ["line", "area", "histogram", "baseline", "candlestick"];

export class ChartArchParser {
    parse(arch, fields = {}) {
        const archInfo = {
            timeField: null,
            seriesFields: [],
            title: "",
        };

        visitXML(arch, (node) => {
            switch (node.tagName) {
                case "chart": {
                    const title = node.getAttribute("string");
                    if (title) {
                        archInfo.title = title;
                    }
                    break;
                }
                case "field": {
                    const fieldName = node.getAttribute("name");
                    const type = node.getAttribute("type");

                    if (type === "time") {
                        archInfo.timeField = fieldName;
                    } else if (SERIES_TYPES.includes(type)) {
                        const string = node.getAttribute("string");
                        archInfo.seriesFields.push({
                            fieldName,
                            type,
                            string: string || fields[fieldName]?.string || fieldName,
                        });
                    }
                    break;
                }
            }
        });

        return archInfo;
    }
}
