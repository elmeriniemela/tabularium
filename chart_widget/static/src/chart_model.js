/** @odoo-module **/

import { Model } from "@web/model/model";
import { getGroupBy } from "@web/search/utils/group_by";

const TYPE_MAP = {
    line: "Line",
    area: "Area",
    histogram: "Histogram",
    baseline: "Baseline",
};

export class ChartModel extends Model {
    setup(params) {
        this.metaData = params;
        this.data = null;
    }

    async load(searchParams) {
        const groupBy = this._getGroupBy(searchParams);
        if (groupBy.length) {
            this.data = await this._loadGroupedSeriesData(searchParams, groupBy);
            return;
        }

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

    _getGroupBy(searchParams) {
        const groupBy = (searchParams.groupBy || []).map((item) =>
            typeof item === "string" ? getGroupBy(item, this.metaData.fields) : item
        );
        if (!groupBy.length) {
            return [];
        }

        const timeGroupBy = groupBy.find((item) => item.fieldName === this.metaData.timeField);
        if (!timeGroupBy) {
            throw new Error(
                `Chart view requires grouping by '${this.metaData.timeField}' when group by filters are active.`
            );
        }

        return [timeGroupBy, ...groupBy.filter((item) => item.fieldName !== this.metaData.timeField)];
    }

    async _loadGroupedSeriesData(searchParams, groupBy) {
        if (this.metaData.seriesFields.some((seriesField) => seriesField.type === "candlestick")) {
            throw new Error("Grouped candlestick charts are not supported.");
        }

        const measures = this.metaData.seriesFields.map((seriesField) =>
            this._getAggregateSpecification(seriesField.fieldName)
        );
        const groups = await this.orm.formattedReadGroup(
            this.metaData.resModel,
            searchParams.domain || [],
            groupBy.map((item) => item.spec),
            measures,
            { context: { fill_temporal: true, ...(searchParams.context || {}) } }
        );

        return this._buildGroupedSeriesData(groups, groupBy);
    }

    _getAggregateSpecification(fieldName) {
        const field = this.metaData.fields[fieldName];
        if (!field.aggregator) {
            throw new Error(
                `No aggregate function has been provided for the series field '${fieldName}'.`
            );
        }
        return `${fieldName}:${field.aggregator}`;
    }

    _buildGroupedSeriesData(groups, groupBy) {
        const { fields, timeField, seriesFields } = this.metaData;
        const timeGroupBy = groupBy[0];
        const seriesByKey = new Map();

        for (const group of groups) {
            const time = this._getGroupedTimeValue(group[timeGroupBy.spec], fields[timeField]?.type);
            if (!time) {
                continue;
            }

            const groupValues = groupBy.slice(1).map((item) => group[item.spec]);
            const groupLabel = groupBy
                .slice(1)
                .map((item) => this._getGroupLabel(group[item.spec], fields[item.fieldName]))
                .filter((label) => label)
                .join(" / ");

            for (const seriesField of seriesFields) {
                const seriesKey = JSON.stringify([seriesField.fieldName, ...groupValues]);
                if (!seriesByKey.has(seriesKey)) {
                    const title = groupLabel
                        ? `${seriesField.string} / ${groupLabel}`
                        : seriesField.string;
                    seriesByKey.set(seriesKey, {
                        type: this._getSeriesType(seriesField.type),
                        data: [],
                        title,
                    });
                }

                const aggregateSpecification = this._getAggregateSpecification(seriesField.fieldName);
                seriesByKey.get(seriesKey).data.push({
                    time,
                    value: group[aggregateSpecification] ?? 0,
                });
            }
        }

        return { series: [...seriesByKey.values()] };
    }

    _getGroupedTimeValue(value, fieldType) {
        const rawValue = Array.isArray(value) ? value[0] : value;
        return this._toTimestamp(rawValue, fieldType === "datetime");
    }

    _getGroupLabel(value) {
        if (value === false || value === null || value === undefined) {
            return "";
        }
        if (Array.isArray(value)) {
            return value[1];
        }
        return `${value}`;
    }

    _getSeriesType(type) {
        return TYPE_MAP[type] || "Line";
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
                    open: r[sf.ohlcFields.open] ?? 0,
                    high: r[sf.ohlcFields.high] ?? 0,
                    low: r[sf.ohlcFields.low] ?? 0,
                    close: r[sf.ohlcFields.close] ?? 0,
                }));
                series.push({ type: "Candlestick", data, title: sf.string });
            } else {
                const data = validRecords.map((r) => ({
                    time: this._toTimestamp(r[timeField], isDatetime),
                    value: r[sf.fieldName] ?? 0,
                }));
                series.push({
                    type: this._getSeriesType(sf.type),
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
