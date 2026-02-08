/** @odoo-module **/

import { loadBundle } from "@web/core/assets";
import { Component, onWillStart, useEffect, useRef, onWillUnmount } from "@odoo/owl";

export class ChartRenderer extends Component {
    static template = "chart_widget.ChartRenderer";
    static props = {
        model: Object,
    };

    setup() {
        this.containerRef = useRef("container");
        this.chart = null;

        onWillStart(async () => {
            await loadBundle("chart_widget.lightweight_charts");
        });

        useEffect(
            () => {
                this._renderChart();
                return () => this._destroyChart();
            },
            () => [this.props.model.data]
        );

        onWillUnmount(() => {
            this._destroyChart();
        });
    }

    _destroyChart() {
        if (this.chart) {
            this.chart.remove();
            this.chart = null;
        }
    }

    _renderChart() {
        const container = this.containerRef.el;
        if (!container) {
            return;
        }

        const data = this.props.model.data;
        if (!data) {
            return;
        }

        this._destroyChart();

        const LWC = window.LightweightCharts;
        if (!LWC) {
            return;
        }

        this.chart = LWC.createChart(container, {
            autoSize: true,
        });

        for (const seriesConfig of data.series) {
            let series;
            const options = {};
            if (seriesConfig.title) {
                options.title = seriesConfig.title;
            }

            switch (seriesConfig.type) {
                case "Candlestick":
                    series = this.chart.addCandlestickSeries(options);
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

            series.setData(seriesConfig.data);
        }

        this.chart.timeScale().fitContent();
    }
}
