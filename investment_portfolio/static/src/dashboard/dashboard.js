/** @odoo-module **/

// https://www.odoo.com/documentation/18.0/developer/tutorials/discover_js_framework/02_build_a_dashboard.html

import { loadBundle } from "@web/core/assets";
import { Component, useState, onWillStart, useEffect, useRef } from "@odoo/owl";
import { Layout } from "@web/search/layout";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

class PositionDashboard extends Component {
    static template = "investment_portfolio.PositionDashboard";
    static components = { Layout };
    // static props = ["*"];

    setup() {
        this.action = useService("action");
        this.display = {
            controlPanel: {},
            searchPanel: false,
        };
        this.state = useState({ value: 0 });
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
            type: 'bar',
            data: {
                labels: ['Red', 'Blue', 'Yellow', 'Green', 'Purple', 'Orange'],
                datasets: [{
                    label: '# of Votes',
                    data: [12, 19, 3, 5, 2, 3],
                    borderWidth: 1
                }]
            },
            options: {
                scales: {
                    y: {
                        beginAtZero: true
                    }
                }
            }
        };
    }

    refresh() {
        this.state.value++;
        // this.action.doAction("investment_portfolio.action_current_positions");
    }
}

registry.category("actions").add("investment_portfolio.dashboard", PositionDashboard);
