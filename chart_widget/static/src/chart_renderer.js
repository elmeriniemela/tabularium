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
            const options = {};
            if (seriesConfig.title) {
                options.title = seriesConfig.title;
            }

            const definition = LWC[`${seriesConfig.type}Series`] || LWC.LineSeries;
            const series = this.chart.addSeries(definition, options);
            series.setData(seriesConfig.data);
        }

        this.chart.timeScale().fitContent();
    }
}
