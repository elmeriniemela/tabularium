# Chart Widget

Adds a `chart` view type to Odoo using the [lightweight-charts](https://github.com/tradingview/lightweight-charts) library (v5.1.0). Supports line, area, histogram, baseline, and candlestick series.

Library documentation: https://tradingview.github.io/lightweight-charts/

## Overview

The module registers `chart` as a new view type alongside list, form, kanban, etc. Chart views are defined with arch XML and integrate with Odoo's search filters and favorites.

## Usage

Define a chart view in XML:

```xml
<record id="view_stock_chart" model="ir.ui.view">
    <field name="name">stock.price.chart</field>
    <field name="model">stock.price</field>
    <field name="arch" type="xml">
        <chart string="Price History">
            <field name="date" type="time"/>
            <field name="close_price" type="line" string="Close"/>
        </chart>
    </field>
</record>
```

### Line chart

```xml
<chart string="Price">
    <field name="date" type="time"/>
    <field name="price" type="line" string="Price"/>
</chart>
```

### Histogram

```xml
<chart string="Volume">
    <field name="date" type="time"/>
    <field name="volume" type="histogram" string="Volume"/>
</chart>
```

### Candlestick (OHLC)

Use `open`, `high`, `low`, `close` field types. They are combined into a single candlestick series automatically.

```xml
<chart string="OHLC">
    <field name="date" type="time"/>
    <field name="open_price" type="open"/>
    <field name="high_price" type="high"/>
    <field name="low_price" type="low"/>
    <field name="close_price" type="close"/>
</chart>
```

### Multiple series

```xml
<chart string="Price and Volume">
    <field name="date" type="time"/>
    <field name="price" type="line" string="Price"/>
    <field name="volume" type="histogram" string="Volume"/>
</chart>
```

## Field types

| `type` attribute | Description |
|---|---|
| `time` | X-axis time field (date or datetime). Required, exactly one per chart. |
| `line` | Line series |
| `area` | Area (filled line) series |
| `histogram` | Bar/histogram series |
| `baseline` | Baseline series (colored above/below a base value) |
| `open` | Open price for candlestick |
| `high` | High price for candlestick |
| `low` | Low price for candlestick |
| `close` | Close price for candlestick |

The `string` attribute on `<field>` sets the series label. The `string` attribute on `<chart>` sets the view title.

## Action setup

Add `chart` to `view_mode` on an action:

```xml
<record id="action_stock_prices" model="ir.actions.act_window">
    <field name="name">Stock Prices</field>
    <field name="res_model">stock.price</field>
    <field name="view_mode">chart,list,form</field>
</record>
```
