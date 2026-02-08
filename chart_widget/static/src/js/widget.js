/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { Component, onMounted, onWillUnmount, onPatched, useRef, onWillStart } from "@odoo/owl";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { loadBundle } from "@web/core/assets";

export class ChartField extends Component {
    static template = "chart_widget.ChartField";
    static props = {
        ...standardFieldProps,
    };

    setup() {
        this.chartRef = useRef("chartContainer");
        this.chart = null;
        this.seriesObjects = [];

        onWillStart(async () => {
            await loadBundle("chart_widget.lightweight_charts");
        });

        onMounted(() => {
            this._renderChart();
        });

        onPatched(() => {
            this._renderChart();
        });

        onWillUnmount(() => {
            this._destroyChart();
        });
    }

    _destroyChart() {
        if (this.chart) {
            this.chart.remove();
            this.chart = null;
            this.seriesObjects = [];
        }
    }

    _parseData() {
        const value = this.props.record.data[this.props.name];
        if (!value) {
            return null;
        }
        try {
            return JSON.parse(value);
        } catch {
            return null;
        }
    }

    _renderChart() {
        const container = this.chartRef.el;
        if (!container) {
            return;
        }

        const data = this._parseData();
        if (!data) {
            this._destroyChart();
            container.innerHTML = "";
            return;
        }

        this._destroyChart();

        const LWC = window.LightweightCharts;
        if (!LWC) {
            return;
        }

        const chartOptions = {
            autoSize: true,
            ...(data.options || {}),
        };

        this.chart = LWC.createChart(container, chartOptions);

        const seriesList = data.series || [];
        for (const seriesConfig of seriesList) {
            const type = seriesConfig.type || "Line";
            const options = seriesConfig.options || {};
            const seriesData = seriesConfig.data || [];

            let series;
            switch (type) {
                case "Candlestick":
                    series = this.chart.addCandlestickSeries(options);
                    break;
                case "Bar":
                    series = this.chart.addBarSeries(options);
                    break;
                case "Area":
                    series = this.chart.addAreaSeries(options);
                    break;
                case "Baseline":
                    series = this.chart.addBaselineSeries(options);
                    break;
                case "Histogram":
                    series = this.chart.addHistogramSeries(options);
                    break;
                case "Line":
                default:
                    series = this.chart.addLineSeries(options);
                    break;
            }

            series.setData(seriesData);
            this.seriesObjects.push(series);
        }

        this.chart.timeScale().fitContent();
    }
}

export const chartField = {
    component: ChartField,
    displayName: _t("Chart"),
    supportedTypes: ["text"],
    extractProps: ({ options }) => ({}),
};

registry.category("fields").add("chart", chartField);
