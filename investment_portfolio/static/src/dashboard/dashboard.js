/** @odoo-module **/

// https://www.odoo.com/documentation/18.0/developer/tutorials/discover_js_framework/02_build_a_dashboard.html

import { _t } from "@web/core/l10n/translation";
import { loadBundle } from "@web/core/assets";
import { Component, useState, onWillStart, onWillUnmount, useEffect, onRendered, useRef } from "@odoo/owl";
import { Layout } from "@web/search/layout";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { formatMonetary, formatPercentage } from "@web/views/fields/formatters";
import { timeago } from "@timeago_widget/timeago/widget"

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

    onClickPosition(record) {
        this.action.doAction({
            type: 'ir.actions.act_window',
            name: record.name,
            target: 'current',
            res_id: record.id,
            res_model: 'investment.position',
            views: [[false, 'form']],
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
                last_update: {},
                last_price: {},
                last_price_own_currency: {},
                is_company_currency: {},
                currency_id: {},
                company_currency_id: {},
                position: {},
                profit: {},
                profit_percent: {},
                daily_price: {},
                weekly_price: {},
                monthly_price: {},
                six_month_price: {},
                ytd_price: {},
                one_year_price: {},
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

            var last_price_own_currency = formatMonetary(record.last_price_own_currency, {
                currencyId: record.company_currency_id,
                digits: 2,
            })
            var last_price = formatMonetary(record.last_price, {
                currencyId: record.currency_id,
                digits: 2,
            })
            positions.push({
                id: record.id,
                name: record.name,
                hasPosition: record.position === 0 ? 1 : 0,
                follow: record.follow ? 1 : 0,
                last_update: timeago(new Date(record.last_update)),
                last_price: record.is_company_currency ? last_price_own_currency : `${last_price} / ${last_price_own_currency}`,
                profit: this.format("monetary", record.profit, true),
                profit_percent: this.format("percentage", record.profit_percent, true),
                position: this.format("monetary", record.position),
                daily_price_abs: Math.abs(record.daily_price), // for sorting
                daily_price: this.format("percentage", record.daily_price, true),
                weekly_price: this.format("percentage", record.weekly_price, true),
                monthly_price: this.format("percentage", record.monthly_price, true),
                six_month_price: this.format("percentage", record.six_month_price, true),
                ytd_price: this.format("percentage", record.ytd_price, true),
                one_year_price: this.format("percentage", record.one_year_price, true),
            });
        }

        var porfolios = Object.entries(pdict).map(([key, value]) => (value));
        porfolios.sort((a, b) => b.position - a.position);

        this.state.liquid.position = this.format("monetary", total_position);
        this.state.liquid.profit = this.format("monetary", total_profit, true);
        this.state.liquid.chart.ids = porfolios.map((x) => x.id);
        this.state.liquid.chart.labels = porfolios.map((x) => x.label);
        this.state.liquid.chart.data = porfolios.map((x) => x.position);

        positions.sort((a, b) => a.hasPosition - b.hasPosition || b.follow - a.follow || b.daily_price_abs - a.daily_price_abs || b.position.value - a.position.value);
        this.state.positions = positions;

    }


    format(type, value, isProfit = false, options = {}) {
        var className = '';
        if (isProfit) {
            if (value >= 0.0001) {
                className = 'text-success';
            } else if (value <= -0.0001) {
                className = 'text-danger';
            }
        }
        switch (type) {
            case "percentage":
                return {
                    value: value,
                    fmtValue: formatPercentage(value, options.digits || 2),
                    className: className,
                }
            case "monetary":
                return {
                    value: value,
                    fmtValue: formatMonetary(value, {
                        currencyId: options.currencyId || 1,
                        digits: options.digits || 2,
                    }),
                    className: className,
                }
            default:
                console.log(`Unknown type for format ${type}.`);
                return {
                    value: value,
                    fmtValue: value,
                    className: className,
                }
        }
    }
}

registry.category("actions").add("investment_portfolio.dashboard", PositionDashboard);
