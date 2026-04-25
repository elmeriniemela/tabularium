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
    close_price = fields.Float({ string: "Close Price", aggregator: "sum" });
    volume = fields.Float({ string: "Volume", aggregator: "sum" });
    open_price = fields.Float({ string: "Open" });
    high_price = fields.Float({ string: "High" });
    low_price = fields.Float({ string: "Low" });

    _records = [
        {
            id: 1,
            date: "2024-01-01",
            close_price: 100,
            volume: 5000,
            open_price: 95,
            high_price: 105,
            low_price: 90,
        },
        {
            id: 2,
            date: "2024-01-02",
            close_price: 110,
            volume: 6000,
            open_price: 100,
            high_price: 115,
            low_price: 98,
        },
        {
            id: 3,
            date: "2024-01-03",
            close_price: 105,
            volume: 4500,
            open_price: 110,
            high_price: 112,
            low_price: 102,
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
        const rpcFields = [];
        onRpc("search_read", ({ kwargs }) => {
            rpcFields.push(...kwargs.fields);
        });

        await mountView({
            type: "chart",
            resModel: "time.series",
            arch: `
                <chart string="OHLC Chart">
                    <field name="date" type="time"/>
                    <field name="open_price" type="open"/>
                    <field name="high_price" type="high"/>
                    <field name="low_price" type="low"/>
                    <field name="close_price" type="close"/>
                </chart>
            `,
        });

        expect(".o_chart_canvas_container").toHaveCount(1);
        expect(rpcFields).toInclude("date");
        expect(rpcFields).toInclude("open_price");
        expect(rpcFields).toInclude("high_price");
        expect(rpcFields).toInclude("low_price");
        expect(rpcFields).toInclude("close_price");
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

    test("arch parser combines OHLC into candlestick", async () => {
        const parser = new ChartArchParser();
        const arch = `
            <chart string="Candlestick">
                <field name="date" type="time"/>
                <field name="open_price" type="open"/>
                <field name="high_price" type="high"/>
                <field name="low_price" type="low"/>
                <field name="close_price" type="close"/>
            </chart>
        `;
        const result = parser.parse(arch);

        expect(result.timeField).toBe("date");
        expect(result.seriesFields).toHaveLength(1);
        expect(result.seriesFields[0].type).toBe("candlestick");
        expect(result.seriesFields[0].ohlcFields.open).toBe("open_price");
        expect(result.seriesFields[0].ohlcFields.high).toBe("high_price");
        expect(result.seriesFields[0].ohlcFields.low).toBe("low_price");
        expect(result.seriesFields[0].ohlcFields.close).toBe("close_price");
        expect(result.seriesFields[0].string).toBe("OHLC");
    });
});
