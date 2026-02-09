/** @odoo-module **/

import { Model } from "@web/model/model";

export class ChartModel extends Model {
    setup(params) {
        this.metaData = params;
        this.data = null;
    }

    async load(searchParams) {
        const { resModel, timeField, seriesFields } = this.metaData;
        const domain = searchParams.domain || [];

        const fieldNames = [timeField];
        for (const sf of seriesFields) {
            if (sf.type === "candlestick") {
                for (const f of Object.values(sf.ohlcFields)) {
                    if (!fieldNames.includes(f)) {
                        fieldNames.push(f);
                    }
                }
            } else {
                if (!fieldNames.includes(sf.fieldName)) {
                    fieldNames.push(sf.fieldName);
                }
            }
        }

        const records = await this.orm.searchRead(
            resModel,
            domain,
            fieldNames,
            { order: `${timeField} asc`, limit: 10000 }
        );

        this.data = this._buildSeriesData(records);
    }

    _buildSeriesData(records) {
        const { timeField, seriesFields, fields } = this.metaData;
        const isDatetime = fields[timeField]?.type === "datetime";

        // Filter records without a time value and deduplicate by time
        // (lightweight-charts requires strictly unique ascending time values)
        const seen = new Set();
        const validRecords = [];
        for (let i = records.length - 1; i >= 0; i--) {
            const r = records[i];
            if (!r[timeField]) {
                continue;
            }
            const time = this._toTimestamp(r[timeField], isDatetime);
            if (!seen.has(time)) {
                seen.add(time);
                validRecords.push(r);
            }
        }
        validRecords.reverse();

        const series = [];

        for (const sf of seriesFields) {
            if (sf.type === "candlestick") {
                const data = validRecords.map((r) => ({
                    time: this._toTimestamp(r[timeField], isDatetime),
                    open: r[sf.ohlcFields.open] || 0,
                    high: r[sf.ohlcFields.high] || 0,
                    low: r[sf.ohlcFields.low] || 0,
                    close: r[sf.ohlcFields.close] || 0,
                }));
                series.push({ type: "Candlestick", data, title: sf.string });
            } else {
                const typeMap = {
                    line: "Line",
                    area: "Area",
                    histogram: "Histogram",
                    baseline: "Baseline",
                };
                const data = validRecords.map((r) => ({
                    time: this._toTimestamp(r[timeField], isDatetime),
                    value: r[sf.fieldName] || 0,
                }));
                series.push({
                    type: typeMap[sf.type] || "Line",
                    data,
                    title: sf.string,
                });
            }
        }

        return { series };
    }

    _toTimestamp(value, isDatetime) {
        if (!value) {
            return 0;
        }
        if (isDatetime) {
            // Odoo datetime format: "YYYY-MM-DD HH:MM:SS" → Unix timestamp
            return Math.floor(new Date(value).getTime() / 1000);
        }
        // Odoo date format: "YYYY-MM-DD" → keep as string for lightweight-charts
        return value;
    }

    hasData() {
        return this.data && this.data.series.some((s) => s.data.length > 0);
    }
}
