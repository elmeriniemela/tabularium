/** @odoo-module **/

import { loadBundle } from "@web/core/assets";
import { Component, onWillStart, useEffect, useRef, onWillUnmount } from "@odoo/owl";

const DECIMAL_HIDING_INTERVAL = 1000;
const INTEGER_PRICE_FORMAT = {
    type: "price",
    precision: 0,
    minMove: 1,
};

export function shouldHidePriceDecimals(visibleRange) {
    return !!visibleRange && Math.abs(visibleRange.to - visibleRange.from) > DECIMAL_HIDING_INTERVAL;
}

export class ChartRenderer extends Component {
    static template = "chart_widget.ChartRenderer";
    static props = {
        model: Object,
    };

    setup() {
        this.containerRef = useRef("container");
        this.chart = null;
        this.renderedSeries = [];
        this.visibleLogicalRangeChangeHandler = null;

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
            if (this.visibleLogicalRangeChangeHandler) {
                this.chart
                    .timeScale()
                    .unsubscribeVisibleLogicalRangeChange(this.visibleLogicalRangeChangeHandler);
                this.visibleLogicalRangeChangeHandler = null;
            }
            this.chart.remove();
            this.chart = null;
        }
        this.renderedSeries = [];
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
            this.renderedSeries.push({
                api: series,
                defaultPriceFormat: { ...series.options().priceFormat },
                hidesDecimals: null,
            });
        }

        const timeScale = this.chart.timeScale();
        this.visibleLogicalRangeChangeHandler = () => this._updatePriceFormats();
        timeScale.subscribeVisibleLogicalRangeChange(this.visibleLogicalRangeChangeHandler);
        timeScale.fitContent();
        this._updatePriceFormats();
    }

    _updatePriceFormats() {
        for (const renderedSeries of this.renderedSeries) {
            const hidesDecimals = shouldHidePriceDecimals(
                renderedSeries.api.priceScale().getVisibleRange()
            );
            if (renderedSeries.hidesDecimals === hidesDecimals) {
                continue;
            }
            renderedSeries.api.applyOptions({
                priceFormat: hidesDecimals
                    ? INTEGER_PRICE_FORMAT
                    : renderedSeries.defaultPriceFormat,
            });
            renderedSeries.hidesDecimals = hidesDecimals;
        }
    }
}
