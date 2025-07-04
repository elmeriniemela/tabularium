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
        this.refreshPortfolios();
        this.refreshPositions();

    }
    async refreshPortfolios() {
        var results = await this.orm.call("investment.position", "web_read_group", [], {
            domain: [["liquid", "=", true]],
            fields: ["position:sum", "profit:sum", "portfolio_id",],
            groupby: ["portfolio_id"],
            lazy: true,
            limit: 10,
            orderby: "position:sum DESC",
        });
        let labels = [];
        let data = [];
        let ids = [];
        let position = 0.0;
        let profit = 0.0;
        for (const group of results.groups) {
            if (group.position !== 0) {
                ids.push(group.portfolio_id[0]);
                labels.push(group.portfolio_id[1]);
                data.push(group.position);
                position += group.position;
            }
            profit += group.profit;
        }
        this.state.liquid.position = formatMonetary(position, {
            currencyId: 1,
            digits: 2,
        });
        this.state.liquid.profit = formatMonetary(profit, {
            currencyId: 1,
            digits: 2,
        });
        this.state.liquid.profitClass = profit >= 0 ? "text-success" : "text-danger";
        this.state.liquid.chart.ids = ids;
        this.state.liquid.chart.labels = labels;
        this.state.liquid.chart.data = data;
    }

    async refreshPositions() {
        var results = await this.orm.call("investment.position", "web_search_read", [], {
            domain: [["liquid", "=", true], ["position", "!=", 0]],
            order: "daily_price_abs DESC, position DESC",
            specification: {
                id: {},
                name: {},
                position: {},
                profit: {},
                daily_price: {},
            }
        });
        let positons = [];
        for (const record of results.records) {
            positons.push({
                id: record.id,
                name: record.name,
                position: formatMonetary(record.position, {
                    currencyId: 1,
                    digits: 2,
                }),
                profit: formatMonetary(record.profit, {
                    currencyId: 1,
                    digits: 2,
                }),
                daily_price: formatPercentage(record.daily_price, 2),
                profitClass: record.profit >= 0 ? "text-success" : "text-danger",
                daily_priceClass: record.daily_price >= 0 ? "text-success" : "text-danger",
            });
        }
        this.state.positions = positons;

    }
}

registry.category("actions").add("investment_portfolio.dashboard", PositionDashboard);
