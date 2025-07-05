/** @odoo-module **/

// https://www.odoo.com/documentation/18.0/developer/tutorials/discover_js_framework/02_build_a_dashboard.html

import { _t } from "@web/core/l10n/translation";
import { loadBundle } from "@web/core/assets";
import { Component, useState, onWillStart, onWillUnmount, useEffect, onRendered, useRef } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { formatMonetary, formatPercentage } from "@web/views/fields/formatters";
import { timeago } from "@timeago_widget/timeago/widget"
import { user } from "@web/core/user";
const { DateTime } = luxon;

class PieChart extends Component {
    static template = "investment_portfolio.PieChart";
    static props = ["labels", "data", "title", "onPieSliceClick", "style"];

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
                        maintainAspectRatio: false,
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


class LineChart extends Component {
    static template = "investment_portfolio.LineChart";
    static props = ["labels", "data", "title", "label", "style"];

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
                    type: 'line',
                    data: {
                        labels: this.props.labels,
                        datasets: [{
                            label: this.props.label,
                            data: this.props.data,
                            borderWidth: 1
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            legend: {
                                position: 'bottom',
                            },
                            title: {
                                display: true,
                                text: this.props.title
                            }
                        },
                    }
                });
            }
        });
    }
}

class PositionDashboard extends Component {
    static template = "investment_portfolio.PositionDashboard";
    static components = { PieChart, LineChart };
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
                    title: _t("Positions"),
                }
            },
            positions: [],
            periods: [],
        });
        this.orm = useService("orm");
        this.userTz = user.tz || luxon.Settings.defaultZone.name;
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

    onClickOpenLiquidPortfolios() {
        return this.action.doAction("investment_portfolio.action_current_positions");
    }

    onClickOpenPosition(record) {
        this.action.doAction({
            type: 'ir.actions.act_window',
            name: record.name,
            target: 'current',
            res_id: record.id,
            res_model: 'investment.position',
            views: [[false, 'form']],
        });
    }

    async onClickRefreshAll(record) {
        var ids = this.state.positions.filter(p => p.hasPosition).map(p => p.id);;
        var prom = this.orm.call("investment.position", "run_integration", [ids]);
        prom.then(() => {
            this.refresh();
        });
    }

    async onClickRefreshPrice(record) {
        var prom = this.orm.call("investment.position", "run_integration", [[record.id]]);
        prom.then((response) => {
            this.refreshPositions();
        })
    }

    async refresh() {
        this.refreshPeriods();
        this.refreshPositions();
    }

    async refreshPeriods() {
        var results = await this.orm.call("investment.period", "get_dashboard", [], {
            domain: [["priority", "=", '1']],
            specification: {
                id: {},
                name: {},
                profit: {},
                annualized_irr: {},
                company_currency_id: {},
            }
        });

        let periods = [];
        for (const record of results.records) {
            periods.push({
                id: record.id,
                name: record.name,
                profit: this.formatField("monetary", record.profit, true, {currencyId: record.company_currency_id}),
                annualized_irr: this.formatField("percentage", record.annualized_irr, true),
            })
        }
        this.state.periods = periods;



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
                endpoint_id: {},
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
                chart_one_month: {},
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

            var last_price_own_currency = this.format("monetary", record.last_price_own_currency, {currencyId: record.company_currency_id})
            var last_price = this.format("monetary", record.last_price, {currencyId: record.currency_id})
            var last_update_date = new Date(DateTime.fromSQL(record.last_update, { zone: "utc" }).setZone(this.userTz));
            if (record.follow) {
                positions.push({
                    id: record.id,
                    name: record.name,
                    hasPosition: record.position === 0 ? 0 : 1,
                    hasEndpoint: record.endpoint_id ? 1 : 0,
                    follow: record.follow ? 1 : 0,
                    last_update: `(${timeago(last_update_date)})`,
                    last_update_iso: last_update_date.toISOString(),
                    last_price: record.is_company_currency ? last_price_own_currency : `${last_price} / ${last_price_own_currency}`,
                    profit: this.formatField("monetary", record.profit, true),
                    profit_percent: this.formatField("percentage", record.profit_percent, true),
                    position: this.formatField("monetary", record.position),
                    mover: Math.abs(record.daily_price* Math.max(record.position, 1)), // for sorting
                    daily_price: this.formatField("percentage", record.daily_price, true),
                    weekly_price: this.formatField("percentage", record.weekly_price, true),
                    monthly_price: this.formatField("percentage", record.monthly_price, true),
                    six_month_price: this.formatField("percentage", record.six_month_price, true),
                    ytd_price: this.formatField("percentage", record.ytd_price, true),
                    one_year_price: this.formatField("percentage", record.one_year_price, true),
                    chart: {
                        data: record.chart_one_month.data,
                        labels: record.chart_one_month.labels,
                        title: _t('1 Month'),
                        label: _t('Price'),
                    }
                });
            }
        }

        var porfolios = Object.entries(pdict).map(([key, value]) => (value));
        porfolios.sort((a, b) => b.position - a.position);

        this.state.liquid.position = this.formatField("monetary", total_position);
        this.state.liquid.profit = this.formatField("monetary", total_profit, true);
        this.state.liquid.chart.ids = porfolios.map((x) => x.id);
        this.state.liquid.chart.labels = porfolios.map((x) => x.label);
        this.state.liquid.chart.data = porfolios.map((x) => x.position);

        positions.sort((a, b) => b.follow - a.follow || b.mover - a.mover || b.hasEndpoint - a.hasEndpoint ||  b.position.value - a.position.value);
        this.state.positions = positions;

    }


    formatField(type, value, isProfit = false, options = {}) {
        var className = '';
        if (isProfit) {
            if (value >= 0.0001) {
                className = 'text-success';
            } else if (value <= -0.0001) {
                className = 'text-danger';
            }
        }

        return {
            value: value,
            fmtValue: this.format(type, value, options),
            className: className,
        }
    }
    format(type, value, options = {}) {
        switch (type) {
            case "percentage":
                return formatPercentage(value, options.digits || 2)
            case "monetary":
                var defaultDigits = [2, 2];
                if (Math.abs(value) >= 1_000) {
                    defaultDigits = [0, 0];
                }
                return formatMonetary(value, {
                    currencyId: options.currencyId || 1,
                    digits: options.digits || defaultDigits,
                })
            default:
                console.log(`Unknown type for format ${type}.`);
                return `${value}`
        }
    }
}

registry.category("actions").add("investment_portfolio.dashboard", PositionDashboard);
