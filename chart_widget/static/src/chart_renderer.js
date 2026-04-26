/** @odoo-module **/

import { loadBundle } from "@web/core/assets";
import { Component, onWillStart, useEffect, useRef, onWillUnmount } from "@odoo/owl";

const PRICE_AXIS_NUMBER_FORMAT = new Intl.NumberFormat("en-US", {
    useGrouping: true,
    maximumFractionDigits: 2,
});

export function formatPriceAxisValue(price) {
    return PRICE_AXIS_NUMBER_FORMAT.format(price);
}

export class ChartRenderer extends Component {
    static template = "chart_widget.ChartRenderer";
    static props = {
        model: Object,
        onPointClick: { type: Function, optional: true },
    };

    setup() {
        this.containerRef = useRef("container");
        this.chart = null;
        this.onChartClick = this._onChartClick.bind(this);

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
            this.chart.unsubscribeClick?.(this.onChartClick);
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
            layout: {
                attributionLogo: false,
            },
            localization: {
                priceFormatter: formatPriceAxisValue,
            },
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

        this.chart.subscribeClick(this.onChartClick);
        this.chart.timeScale().fitContent();
    }

    _onChartClick(param) {
        const point =
            (param.hoveredSeries && param.seriesData.get(param.hoveredSeries)) ||
            [...param.seriesData.values()].find((item) => item?.customValues?.domain !== undefined);
        const domain = point?.customValues?.domain;
        if (domain !== undefined) {
            this.props.onPointClick?.(domain);
        }
    }
}
