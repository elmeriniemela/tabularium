/** @odoo-module **/

// https://www.odoo.com/documentation/18.0/developer/tutorials/discover_js_framework/02_build_a_dashboard.html

import { loadBundle } from "@web/core/assets";
import { Component, useState, onWillStart, useEffect, useRef } from "@odoo/owl";
import { Layout } from "@web/search/layout";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { formatMonetary } from "@web/views/fields/formatters";

class PositionDashboard extends Component {
    static template = "investment_portfolio.PositionDashboard";
    static components = { Layout };
    static props = ["*"];

    setup() {
        this.action = useService("action");
        this.display = {
            controlPanel: {},
            searchPanel: false,
        };
        this.state = useState({
            liquid: {
                position: 0.0,
                profit: 0.0,
                chart: {
                    labels: [],
                    data: [],
                }
            }
        });
        this.orm = useService("orm");

        this.chart = null;
        this.canvasRef = useRef("canvas");
        onWillStart(async () => await loadBundle("web.chartjs_lib"));
        useEffect(() => {
            this.renderChart();
            return () => {
                if (this.chart) {
                    this.chart.destroy();
                }
            };
        });
        this.refresh();

    }

    renderChart() {
        if (this.chart) {
            this.chart.destroy();
        }
        let config;
        config = this.getLineChartConfig();
        this.chart = new Chart(this.canvasRef.el, config);
    }

    getLineChartConfig() {
        return {
            type: 'pie',
            data: {
                labels: this.state.liquid.chart.labels,
                datasets: [{
                    // label: '',
                    data: this.state.liquid.chart.data,
                    borderWidth: 1
                }]
            },
            options: {
                responsive: true,
                plugins: {
                legend: {
                    position: 'top',
                },
                title: {
                    display: true,
                    text: 'Positions'
                }
                }
            }
        };
    }

    async refresh() {
        // this.action.doAction("investment_portfolio.action_current_positions");
        var results = await this.orm.call("investment.position", "web_read_group", [], {
            domain: [["liquid", "=", true], ["position", "!=", 0]],
            fields: ["position:sum", "profit:sum", "portfolio_id",],
            groupby: ["portfolio_id"],
            lazy: true,
            limit: 10,
            orderby: "position:sum DESC",
        });

        let labels = [];
        let data = [];
        let position = 0.0;
        let profit = 0.0;
        for (const group of results.groups) {
            labels.push(group.portfolio_id[1]);
            data.push(group.position);
            position += group.position;
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
        this.state.liquid.chart.labels = labels;
        this.state.liquid.chart.data = data;
    }
}

registry.category("actions").add("investment_portfolio.dashboard", PositionDashboard);
