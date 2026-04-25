/** @odoo-module **/

import { Model } from "@web/model/model";
import { getGroupBy } from "@web/search/utils/group_by";

const TYPE_MAP = {
    line: "Line",
    area: "Area",
    histogram: "Histogram",
    baseline: "Baseline",
    candlestick: "Candlestick",
};

export class ChartModel extends Model {
    setup(params) {
        this.metaData = params;
        this.data = null;
    }

    async load(searchParams) {
        const groupBy = this._getEffectiveGroupBy(searchParams);
        if (groupBy.length) {
            this.data = await this._loadGroupedSeriesData(searchParams, groupBy);
            return;
        }

        const { resModel, timeField, seriesFields } = this.metaData;
        const domain = searchParams.domain || [];

        const fieldNames = [timeField];
        for (const sf of seriesFields) {
            if (!fieldNames.includes(sf.fieldName)) {
                fieldNames.push(sf.fieldName);
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

    _getEffectiveGroupBy(searchParams) {
        const groupBy = this._getGroupBy(searchParams);
        if (groupBy.length || !this._hasCandlestickSeries()) {
            return groupBy;
        }
        return [getGroupBy(`${this.metaData.timeField}:day`, this.metaData.fields)];
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

    _hasCandlestickSeries() {
        return this.metaData.seriesFields.some((seriesField) => seriesField.type === "candlestick");
    }

    async _loadGroupedSeriesData(searchParams, groupBy) {
        const measures = [];
        for (const seriesField of this.metaData.seriesFields) {
            for (const measure of this._getGroupedMeasureSpecifications(seriesField)) {
                if (!measures.includes(measure)) {
                    measures.push(measure);
                }
            }
        }
        const groups = await this.orm.formattedReadGroup(
            this.metaData.resModel,
            searchParams.domain || [],
            groupBy.map((item) => item.spec),
            measures,
            { context: { fill_temporal: true, ...(searchParams.context || {}) } }
        );

        return this._buildGroupedSeriesData(groups, groupBy);
    }

    _getGroupedMeasureSpecifications(seriesField) {
        if (seriesField.type !== "candlestick") {
            return [this._getAggregateSpecification(seriesField.fieldName)];
        }
        return [
            `${this.metaData.timeField}:array_agg`,
            "id:array_agg",
            `${seriesField.fieldName}:array_agg`,
            `${seriesField.fieldName}:max`,
            `${seriesField.fieldName}:min`,
        ];
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
        const isDatetime = fields[timeField]?.type === "datetime";
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

                const point =
                    seriesField.type === "candlestick"
                        ? this._getGroupedCandlestickPoint(group, seriesField, time, isDatetime)
                        : {
                              time,
                              value:
                                  group[this._getAggregateSpecification(seriesField.fieldName)] ?? 0,
                          };
                if (point) {
                    seriesByKey.get(seriesKey).data.push(point);
                }
            }
        }

        return { series: [...seriesByKey.values()] };
    }

    _getGroupedCandlestickPoint(group, seriesField, time, isDatetime) {
        const timeValues = group[`${this.metaData.timeField}:array_agg`] || [];
        const recordIds = group["id:array_agg"] || [];
        const values = group[`${seriesField.fieldName}:array_agg`] || [];

        if (timeValues.length !== values.length || recordIds.length !== values.length) {
            throw new Error(`Invalid candlestick group data for '${seriesField.fieldName}'.`);
        }
        if (!values.length) {
            return null;
        }

        const orderedValues = values
            .map((value, index) => ({
                id: recordIds[index],
                time: this._toTimestamp(timeValues[index], isDatetime),
                value: value ?? 0,
            }))
            .sort((left, right) => {
                if (left.time < right.time) {
                    return -1;
                }
                if (left.time > right.time) {
                    return 1;
                }
                return left.id - right.id;
            });

        return {
            time,
            open: orderedValues[0].value,
            high: group[`${seriesField.fieldName}:max`] ?? orderedValues[0].value,
            low: group[`${seriesField.fieldName}:min`] ?? orderedValues[0].value,
            close: orderedValues[orderedValues.length - 1].value,
        };
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
