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
                                display: false,
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

    async onClickRefreshAll() {
        var ids = this.state.positions.filter(p => p.hasPosition).map(p => p.id);;
        var prom = this.orm.call("investment.position", "run_integration", [ids]);
        prom.then(() => {
            this.refresh();
        });
    }

    async onClickPriceChange(record, field) {
        var prom = this.orm.call("investment.position", "action_show_price_change", [[record.id], field]);
        prom.then((response) => {
            this.action.doAction(response);
        });
    }

    async onClickProfitChange(record, field) {
        var prom = this.orm.call("investment.position", "action_show_profit_change", [[record.id], field]);
        prom.then((response) => {
            this.action.doAction(response);
        });
    }

    async onClickRefreshPrice(record) {
        var prom = this.fetchPositions([['id', '=', record.id]], true);
        prom.then((results) => {
            for (const record of results.records) {
                var update = this.state.positions.find((pos) => pos.id === record.id) // hash map would be faster, but there aren't more than 100's of positions to track usually
                Object.assign(update, this.recToPosition(record))
            }
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


    async fetchPositions(domain=[], run_integration=false) {
        return this.orm.call("investment.position", "get_dashboard", [], {
            domain: ([["liquid", "=", true]].concat(domain)),
            run_integration: run_integration,
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
                five_year_price: {},
                daily_profit: {},
                weekly_profit: {},
                monthly_profit: {},
                six_month_profit: {},
                ytd_profit: {},
                one_year_profit: {},
                five_year_profit: {},
                chart_one_month: {},
                portfolio_id: { fields: { display_name: {} } },
            }
        });
    }

    recToPosition(record) {
        var last_price_own_currency = this.format("monetary", record.last_price_own_currency, {currencyId: record.company_currency_id})
        var last_price = this.format("monetary", record.last_price, {currencyId: record.currency_id})
        var last_update_date = new Date(DateTime.fromSQL(record.last_update, { zone: "utc" }).setZone(this.userTz));
        return {
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
            five_year_price: this.formatField("percentage", record.five_year_price, true),
            daily_profit: this.formatField("monetary", record.daily_profit, true, {currencyId: record.company_currency_id}),
            weekly_profit: this.formatField("monetary", record.weekly_profit, true, {currencyId: record.company_currency_id}),
            monthly_profit: this.formatField("monetary", record.monthly_profit, true, {currencyId: record.company_currency_id}),
            six_month_profit: this.formatField("monetary", record.six_month_profit, true, {currencyId: record.company_currency_id}),
            ytd_profit: this.formatField("monetary", record.ytd_profit, true, {currencyId: record.company_currency_id}),
            one_year_profit: this.formatField("monetary", record.one_year_profit, true, {currencyId: record.company_currency_id}),
            five_year_profit: this.formatField("monetary", record.five_year_profit, true, {currencyId: record.company_currency_id}),
            chart: {
                data: record.chart_one_month.data,
                labels: record.chart_one_month.labels,
                title: _t('1 Month'),
                label: _t('Price'),
            }
        }

    }

    async refreshPositions() {
        var results = await this.fetchPositions();
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
            if (record.follow) {
                positions.push(this.recToPosition(record));
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
                var defaultDigits = [2, 2];
                if (Math.abs(value) >= 10) {
                    defaultDigits = [0, 0];
                    value = Number.parseFloat((value*100).toFixed(0)) / 100
                }
                return formatPercentage(value, options.digits || defaultDigits)
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
