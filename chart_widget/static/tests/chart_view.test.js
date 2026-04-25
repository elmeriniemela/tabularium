/** @odoo-module **/

import { describe, expect, test } from "@odoo/hoot";
import {
    defineModels,
    fields,
    models,
    mountView,
    onRpc,
    toggleMenuItem,
    toggleSearchBarMenu,
} from "@web/../tests/web_test_helpers";
import { ChartArchParser } from "@chart_widget/chart_arch_parser";
import { ChartModel } from "@chart_widget/chart_model";

class TimeSeries extends models.Model {
    _name = "time.series";

    date = fields.Date({ string: "Date" });
    moment = fields.Datetime({ string: "Moment" });
    price = fields.Float({ string: "Price" });
    close_price = fields.Float({ string: "Close Price", aggregator: "sum" });
    volume = fields.Float({ string: "Volume", aggregator: "sum" });

    _records = [
        {
            id: 1,
            date: "2024-01-01",
            moment: "2024-01-01 09:00:00",
            price: 95,
            close_price: 100,
            volume: 5000,
        },
        {
            id: 2,
            date: "2024-01-01",
            moment: "2024-01-01 11:00:00",
            price: 105,
            close_price: 110,
            volume: 6000,
        },
        {
            id: 3,
            date: "2024-01-01",
            moment: "2024-01-01 10:00:00",
            price: 90,
            close_price: 105,
            volume: 4500,
        },
        {
            id: 4,
            date: "2024-01-02",
            moment: "2024-01-02 09:00:00",
            price: 110,
            close_price: 115,
            volume: 5500,
        },
        {
            id: 5,
            date: "2024-01-03",
            moment: "2024-01-02 15:00:00",
            price: 100,
            close_price: 120,
            volume: 6500,
        },
    ];

    _views = {
        chart: `
            <chart string="Test Chart">
                <field name="date" type="time"/>
                <field name="close_price" type="line" string="Close"/>
            </chart>
        `,
        search: `<search/>`,
    };
}

defineModels([TimeSeries]);

describe("chart view", () => {
    test("load chart view", async () => {
        await mountView({
            type: "chart",
            resModel: "time.series",
        });

        expect(".o_chart_renderer").toHaveCount(1);
        expect(".o_chart_canvas_container").toHaveCount(1);
    });

    test("render with line series", async () => {
        const rpcFields = [];
        onRpc("search_read", ({ kwargs }) => {
            rpcFields.push(...kwargs.fields);
            expect.step("search_read");
        });

        await mountView({
            type: "chart",
            resModel: "time.series",
            arch: `
                <chart string="Line Chart">
                    <field name="date" type="time"/>
                    <field name="close_price" type="line" string="Close"/>
                </chart>
            `,
        });

        expect(".o_chart_canvas_container").toHaveCount(1);
        expect.verifySteps(["search_read"]);
        expect(rpcFields).toInclude("date");
        expect(rpcFields).toInclude("close_price");
    });

    test("render with candlestick series", async () => {
        onRpc("formatted_read_group", ({ kwargs }) => {
            expect.step("formatted_read_group");
            expect(kwargs.groupby).toEqual(["moment:day"]);
            expect(kwargs.aggregates).toEqual([
                "moment:array_agg",
                "id:array_agg",
                "price:array_agg",
                "price:max",
                "price:min",
            ]);
            return [];
        });
        onRpc("search_read", () => {
            expect.step("search_read");
            return [];
        });

        await mountView({
            type: "chart",
            resModel: "time.series",
            arch: `
                <chart string="Candlestick Chart">
                    <field name="moment" type="time"/>
                    <field name="price" type="candlestick"/>
                </chart>
            `,
        });

        expect(".o_chart_canvas_container").toHaveCount(1);
        expect.verifySteps(["formatted_read_group"]);
    });

    test("render with histogram series", async () => {
        const rpcFields = [];
        onRpc("search_read", ({ kwargs }) => {
            rpcFields.push(...kwargs.fields);
        });

        await mountView({
            type: "chart",
            resModel: "time.series",
            arch: `
                <chart string="Volume Chart">
                    <field name="date" type="time"/>
                    <field name="volume" type="histogram" string="Volume"/>
                </chart>
            `,
        });

        expect(".o_chart_canvas_container").toHaveCount(1);
        expect(rpcFields).toInclude("date");
        expect(rpcFields).toInclude("volume");
    });

    test("responds to search filters", async () => {
        let searchReadCount = 0;
        onRpc("search_read", () => {
            searchReadCount++;
        });

        await mountView({
            type: "chart",
            resModel: "time.series",
            arch: `
                <chart string="Test Chart">
                    <field name="date" type="time"/>
                    <field name="close_price" type="line" string="Close"/>
                </chart>
            `,
            searchViewArch: `
                <search>
                    <filter name="high_volume" string="High Volume" domain="[('volume', '>', 5000)]"/>
                </search>
            `,
        });

        const initialCount = searchReadCount;
        await toggleSearchBarMenu();
        await toggleMenuItem("High Volume");
        expect(searchReadCount).toBeGreaterThan(initialCount);
    });

    test("activates default time group by filters", async () => {
        onRpc("formatted_read_group", ({ kwargs }) => {
            expect.step("formatted_read_group");
            expect(kwargs.groupby).toEqual(["date:day"]);
            expect(kwargs.aggregates).toEqual(["close_price:sum"]);
            return [];
        });
        onRpc("search_read", () => {
            expect.step("search_read");
            return [];
        });

        await mountView({
            type: "chart",
            resModel: "time.series",
            arch: `
                <chart string="Grouped Chart">
                    <field name="date" type="time"/>
                    <field name="close_price" type="line" string="Close"/>
                </chart>
            `,
            searchViewArch: `
                <search>
                    <group>
                        <filter name="group_day" string="Date" context="{'group_by': 'date:day'}"/>
                    </group>
                </search>
            `,
            context: {
                search_default_group_day: 1,
            },
        });

        expect.verifySteps(["formatted_read_group"]);
    });

    test("aggregates series by the active time group", async () => {
        const model = Object.create(ChartModel.prototype);
        model.metaData = {
            fields: {
                date: { type: "date" },
                close_price: { type: "float", aggregator: "sum" },
            },
            resModel: "time.series",
            timeField: "date",
            seriesFields: [
                {
                    fieldName: "close_price",
                    type: "line",
                    string: "Close",
                },
            ],
        };
        model.orm = {
            formattedReadGroup: async (resModel, domain, groupBy, aggregates) => {
                expect(resModel).toBe("time.series");
                expect(domain).toEqual([]);
                expect.step("formatted_read_group");
                expect(groupBy).toEqual(["date:day"]);
                expect(aggregates).toEqual(["close_price:sum"]);
                return [
                    {
                        "__count": 2,
                        "__extra_domain": [["date", "=", "2024-01-01"]],
                        "date:day": ["2024-01-01", "01 Jan 2024"],
                        "close_price:sum": 210,
                    },
                    {
                        "__count": 1,
                        "__extra_domain": [["date", "=", "2024-01-02"]],
                        "date:day": ["2024-01-02", "02 Jan 2024"],
                        "close_price:sum": 110,
                    },
                ];
            },
            searchRead: async () => {
                expect.step("search_read");
                return [];
            },
        };

        await model.load({
            context: {},
            domain: [],
            groupBy: ["date:day"],
        });

        expect.verifySteps(["formatted_read_group"]);
        expect(model.data.series).toHaveLength(1);
        expect(model.data.series[0].type).toBe("Line");
        expect(model.data.series[0].data).toEqual([
            { time: "2024-01-01", value: 210 },
            { time: "2024-01-02", value: 110 },
        ]);
    });

    test("aggregates candlestick series from grouped values", async () => {
        const model = Object.create(ChartModel.prototype);
        model.metaData = {
            fields: {
                moment: { type: "datetime" },
                price: { type: "float", aggregator: "sum" },
            },
            resModel: "time.series",
            timeField: "moment",
            seriesFields: [
                {
                    fieldName: "price",
                    type: "candlestick",
                    string: "Price",
                },
            ],
        };
        model.orm = {
            formattedReadGroup: async (resModel, domain, groupBy, aggregates) => {
                expect(resModel).toBe("time.series");
                expect(domain).toEqual([]);
                expect.step("formatted_read_group");
                expect(groupBy).toEqual(["moment:day"]);
                expect(aggregates).toEqual([
                    "moment:array_agg",
                    "id:array_agg",
                    "price:array_agg",
                    "price:max",
                    "price:min",
                ]);
                return [
                    {
                        "__count": 3,
                        "__extra_domain": [["moment", ">=", "2024-01-01 00:00:00"]],
                        "moment:day": ["2024-01-01", "01 Jan 2024"],
                        "moment:array_agg": [
                            "2024-01-01 11:00:00",
                            "2024-01-01 09:00:00",
                            "2024-01-01 10:00:00",
                        ],
                        "id:array_agg": [1, 2, 3],
                        "price:array_agg": [105, 95, 90],
                        "price:max": 105,
                        "price:min": 90,
                    },
                    {
                        "__count": 2,
                        "__extra_domain": [["moment", ">=", "2024-01-02 00:00:00"]],
                        "moment:day": ["2024-01-02", "02 Jan 2024"],
                        "moment:array_agg": [
                            "2024-01-02 09:00:00",
                            "2024-01-02 15:00:00",
                        ],
                        "id:array_agg": [4, 5],
                        "price:array_agg": [110, 100],
                        "price:max": 110,
                        "price:min": 100,
                    },
                ];
            },
            searchRead: async () => {
                expect.step("search_read");
                return [];
            },
        };

        await model.load({
            context: {},
            domain: [],
            groupBy: [],
        });

        expect.verifySteps(["formatted_read_group"]);
        expect(model.data.series).toHaveLength(1);
        expect(model.data.series[0].type).toBe("Candlestick");
        expect(model.data.series[0].data).toEqual([
            {
                time: Math.floor(new Date("2024-01-01").getTime() / 1000),
                open: 95,
                high: 105,
                low: 90,
                close: 105,
            },
            {
                time: Math.floor(new Date("2024-01-02").getTime() / 1000),
                open: 110,
                high: 110,
                low: 100,
                close: 100,
            },
        ]);
    });

    test("no data displays helper", async () => {
        TimeSeries._records = [];

        await mountView({
            type: "chart",
            resModel: "time.series",
        });

        expect(".o_view_nocontent").toHaveCount(1);
    });
});

describe("chart arch parser", () => {
    test("arch parser extracts fields correctly", async () => {
        const parser = new ChartArchParser();
        const arch = `
            <chart string="My Chart">
                <field name="date" type="time"/>
                <field name="close_price" type="line" string="Close"/>
                <field name="volume" type="histogram" string="Volume"/>
            </chart>
        `;
        const result = parser.parse(arch);

        expect(result.title).toBe("My Chart");
        expect(result.timeField).toBe("date");
        expect(result.seriesFields).toHaveLength(2);
        expect(result.seriesFields[0].fieldName).toBe("close_price");
        expect(result.seriesFields[0].type).toBe("line");
        expect(result.seriesFields[0].string).toBe("Close");
        expect(result.seriesFields[1].fieldName).toBe("volume");
        expect(result.seriesFields[1].type).toBe("histogram");
        expect(result.seriesFields[1].string).toBe("Volume");
    });

    test("arch parser reads candlestick fields", async () => {
        const parser = new ChartArchParser();
        const arch = `
            <chart string="Candlestick">
                <field name="moment" type="time"/>
                <field name="price" type="candlestick" string="Price"/>
            </chart>
        `;
        const result = parser.parse(arch);

        expect(result.timeField).toBe("moment");
        expect(result.seriesFields).toHaveLength(1);
        expect(result.seriesFields[0].type).toBe("candlestick");
        expect(result.seriesFields[0].fieldName).toBe("price");
        expect(result.seriesFields[0].string).toBe("Price");
    });
});
