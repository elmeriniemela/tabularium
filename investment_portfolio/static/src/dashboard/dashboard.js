/** @odoo-module **/

// https://www.odoo.com/documentation/18.0/developer/tutorials/discover_js_framework/02_build_a_dashboard.html

import { _t } from "@web/core/l10n/translation";
import { loadBundle } from "@web/core/assets";
import { Component, useState, onWillStart, onWillUnmount, useEffect, onRendered, useRef } from "@odoo/owl";
import { Layout } from "@web/search/layout";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { formatMonetary, formatPercentage } from "@web/views/fields/formatters";

class PieChart extends Component {
    static template = "investment_portfolio.PieChart";
    static props = ["labels", "data", "title", "onPieSliceClick"];

    setup() {
        this.chart = null;
        this.canvasRef = useRef("canvas");
        onWillStart(async () => {
            await loadBundle("web.chartjs_lib");
        });
        onWillUnmount(() => {
            if (this.chart) {
                this.chart.destroy();
            }
        });
        useEffect(() => {
            if (this.chart) {
                this.chart.destroy();
            }
            if (this.canvasRef.el) {
                this.chart = new Chart(this.canvasRef.el, {
                    type: 'pie',
                    data: {
                        labels: this.props.labels,
                        datasets: [{
                            data: this.props.data,
                            borderWidth: 1
                        }]
                    },
                    options: {
                        responsive: true,
                        plugins: {
                            legend: {
                                position: 'bottom',
                            },
                            title: {
                                display: true,
                                text: this.props.title
                            }
                        },
                        onClick: (event, elements) => {
                            if (elements.length) {
                                const idx = elements[0].index;
                                this.props.onPieSliceClick(idx);
                            }
                        }

                    }
                });
            }
        });
    }
}

class PositionDashboard extends Component {
    static template = "investment_portfolio.PositionDashboard";
    static components = { PieChart };
    static props = ["*"];

    setup() {
        this.action = useService("action");
        this.state = useState({
            liquid: {
                position: 0.0,
                profit: 0.0,
                chart: {
                    labels: [],
                    data: [],
                    ids: [],
                    title: "Positions",
                }
            },
            positions: [],
        });
        this.orm = useService("orm");
        this.refresh();
    }

    onPieSliceClick(idx) {
        this.action.doAction({
            type: 'ir.actions.act_window',
            name: this.state.liquid.chart.labels[idx],
            target: 'current',
            context: {
                search_default_portfolio_id: this.state.liquid.chart.ids[idx],
                search_default_group_name: 1,
            },
            res_model: 'investment.position',
            views: [[false, 'graph']],
        });
    }

    async refresh() {
        this.refreshPositions();
    }

    async refreshPositions() {
        var results = await this.orm.call("investment.position", "web_search_read", [], {
            domain: [["liquid", "=", true]],
            order: "position DESC",
            specification: {
                id: {},
                name: {},
                follow: {},
                position: {},
                profit: {},
                daily_price: {},
                portfolio_id: { fields: { display_name: {} } },
            }
        });
        let positions = [];
        let pdict = {};
        let total_position = 0.0;
        let total_profit = 0.0;
        for (const record of results.records) {
            total_position += record.position;
            total_profit += record.profit;
            var pid = record.portfolio_id.id;
            var pname = record.portfolio_id.display_name;

            if (record.position !== 0) {
                var obj = pdict[pid] || {};
                obj.position = (obj.position || 0) + record.position;
                obj.label = pname;
                obj.id = pid;
                pdict[pid] = obj;
            }

            positions.push({
                id: record.id,
                name: record.name,
                hasPosition: record.position === 0 ? 1: 0,
                follow: record.follow ? 1: 0,
                position: this.format("monetary", record.position),
                profit: this.format("monetary", record.profit, true),
                daily_price: this.format("percentage", record.daily_price, true),
                daily_price_abs: this.format("percentage", Math.abs(record.daily_price)),
            });
        }

        var porfolios = Object.entries(pdict).map(([key, value]) => (value));
        porfolios.sort((a, b) => b.position - a.position);

        this.state.liquid.position = this.format("monetary", total_position);
        this.state.liquid.profit = this.format("monetary", total_profit, true);
        this.state.liquid.chart.ids = porfolios.map((x) => x.id);
        this.state.liquid.chart.labels = porfolios.map((x) => x.label);
        this.state.liquid.chart.data = porfolios.map((x) => x.position);

        positions.sort((a, b) =>  a.hasPosition - b.hasPosition || b.follow - a.follow || b.daily_price_abs.value - a.daily_price_abs.value || b.position.value - a.position.value);
        this.state.positions = positions;

    }


    format(type, value, isProfit=false) {
        let profitClass = isProfit ? value >= 0 ? "text-success" : "text-danger": '';
        switch (type) {
            case "percentage":
                return {
                    value: value,
                    fmtValue: formatPercentage(value, 2),
                    className: profitClass,
                }
            case "monetary":
                return {
                    value: value,
                    fmtValue: formatMonetary(value, {
                        currencyId: 1,
                        digits: 2,
                    }),
                    className: profitClass,
                }
            default:
                console.log(`Unknown type for format ${type}.`);
                return {
                    value: value,
                    fmtValue: value,
                    className: profitClass,
                }
        }

    }
}

registry.category("actions").add("investment_portfolio.dashboard", PositionDashboard);
