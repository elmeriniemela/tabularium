# -*- coding: utf-8 -*-

from odoo import fields, models, tools


class InvestmentTotalTimeseries(models.Model):
    _name = 'investment.total.timeseries'
    _description = 'Investment Total Time Series'
    _auto = False
    _rec_name = 'time'
    _order = 'time desc, id desc'

    time = fields.Datetime(readonly=True)
    position = fields.Float(
        readonly=True,
        aggregator='avg',
    )

    def init(self):
        self.env.cr.execute("""
            CREATE INDEX IF NOT EXISTS investment_asset_price_actual_asset_time_idx
                ON investment_asset_price (asset_id, time)
                WHERE interpolated IS NOT TRUE
                    AND prediction IS NOT TRUE
        """)
        self.env.cr.execute("""
            CREATE INDEX IF NOT EXISTS investment_position_transaction_record_position_time_idx
                ON investment_position_transaction (position_id, time)
                WHERE usage = 'record'
        """)
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(f"""
            CREATE OR REPLACE VIEW {self._table} AS (
                WITH qualifying_asset AS (
                    SELECT
                        DISTINCT pos.asset_id
                    FROM investment_position AS pos
                    JOIN investment_asset AS asset
                        ON asset.id = pos.asset_id
                    JOIN investment_category AS category
                        ON category.id = asset.category_id
                    WHERE category.liquid IS TRUE
                        AND pos.company_id = 1
                ),
                asset_price_event AS (
                    SELECT
                        price.asset_id,
                        price.time,
                        price.id AS price_event_id,
                        price.price
                    FROM investment_asset_price AS price
                    JOIN qualifying_asset AS asset
                        ON asset.asset_id = price.asset_id
                    WHERE price.interpolated IS NOT TRUE
                        AND price.prediction IS NOT TRUE
                ),
                asset_quantity_event AS (
                    SELECT
                        pos.asset_id,
                        tx.time,
                        SUM(tx.quantity) AS quantity_delta
                    FROM investment_position_transaction AS tx
                    JOIN investment_position AS pos
                        ON pos.id = tx.position_id
                    JOIN qualifying_asset AS asset
                        ON asset.asset_id = pos.asset_id
                    WHERE tx.usage = 'record'
                        AND pos.company_id = 1
                    GROUP BY
                        pos.asset_id,
                        tx.time
                ),
                asset_event AS (
                    SELECT
                        event.asset_id,
                        event.time,
                        MAX(event.price_event_id) AS price_event_id,
                        SUM(event.quantity_delta) AS quantity_delta
                    FROM (
                        SELECT
                            price.asset_id,
                            price.time,
                            price.price_event_id,
                            0.0 AS quantity_delta
                        FROM asset_price_event AS price
                        UNION ALL
                        SELECT
                            quantity.asset_id,
                            quantity.time,
                            NULL AS price_event_id,
                            quantity.quantity_delta
                        FROM asset_quantity_event AS quantity
                    ) AS event
                    GROUP BY
                        event.asset_id,
                        event.time
                ),
                asset_state AS (
                    SELECT
                        event.asset_id,
                        event.time,
                        event.price_event_id,
                        SUM(event.quantity_delta) OVER (
                            PARTITION BY event.asset_id
                            ORDER BY event.time
                            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                        ) AS quantity,
                        MAX(CASE
                            WHEN event.price_event_id IS NOT NULL
                            THEN event.time
                        END) OVER (
                            PARTITION BY event.asset_id
                            ORDER BY event.time
                            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                        ) AS price_time
                    FROM asset_event AS event
                ),
                asset_value_event AS (
                    SELECT
                        state.asset_id,
                        state.time,
                        state.price_event_id,
                        COALESCE(state.quantity, 0.0) * COALESCE(price.price, 0.0) AS position
                    FROM asset_state AS state
                    LEFT JOIN asset_price_event AS price
                        ON price.asset_id = state.asset_id
                        AND price.time = state.price_time
                ),
                asset_value_delta AS (
                    SELECT
                        event.asset_id,
                        event.time,
                        event.price_event_id,
                        event.position
                            - COALESCE(LAG(event.position) OVER (
                                PARTITION BY event.asset_id
                                ORDER BY event.time
                            ), 0.0) AS delta_position
                    FROM asset_value_event AS event
                ),
                portfolio_event AS (
                    SELECT
                        event.time,
                        BOOL_OR(event.price_event_id IS NOT NULL) AS has_price_event,
                        SUM(event.delta_position) AS delta_position
                    FROM asset_value_delta AS event
                    GROUP BY event.time
                ),
                portfolio_tick AS (
                    SELECT
                        event.time,
                        event.has_price_event,
                        SUM(event.delta_position) OVER (
                            ORDER BY event.time
                            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                        ) AS position
                    FROM portfolio_event AS event
                ),
                daily_tick AS (
                    SELECT
                        tick.time,
                        tick.time::date AS day,
                        tick.position
                    FROM portfolio_tick AS tick
                    WHERE tick.has_price_event IS TRUE
                ),
                open_tick AS (
                    SELECT
                        day,
                        time,
                        position,
                        1 AS slot
                    FROM (
                        SELECT
                            tick.*,
                            ROW_NUMBER() OVER (
                                PARTITION BY tick.day
                                ORDER BY tick.time
                            ) AS rownum
                        FROM daily_tick AS tick
                    ) AS ranked
                    WHERE ranked.rownum = 1
                ),
                high_tick AS (
                    SELECT
                        day,
                        time,
                        position,
                        2 AS slot
                    FROM (
                        SELECT
                            tick.*,
                            ROW_NUMBER() OVER (
                                PARTITION BY tick.day
                                ORDER BY
                                    tick.position DESC,
                                    tick.time
                            ) AS rownum
                        FROM daily_tick AS tick
                    ) AS ranked
                    WHERE ranked.rownum = 1
                ),
                low_tick AS (
                    SELECT
                        day,
                        time,
                        position,
                        3 AS slot
                    FROM (
                        SELECT
                            tick.*,
                            ROW_NUMBER() OVER (
                                PARTITION BY tick.day
                                ORDER BY
                                    tick.position,
                                    tick.time
                            ) AS rownum
                        FROM daily_tick AS tick
                    ) AS ranked
                    WHERE ranked.rownum = 1
                ),
                close_tick AS (
                    SELECT
                        day,
                        time,
                        position,
                        4 AS slot
                    FROM (
                        SELECT
                            tick.*,
                            ROW_NUMBER() OVER (
                                PARTITION BY tick.day
                                ORDER BY tick.time DESC
                            ) AS rownum
                        FROM daily_tick AS tick
                    ) AS ranked
                    WHERE ranked.rownum = 1
                ),
                daily_ohlc AS (
                    SELECT * FROM open_tick
                    UNION ALL
                    SELECT * FROM high_tick
                    UNION ALL
                    SELECT * FROM low_tick
                    UNION ALL
                    SELECT * FROM close_tick
                )
                SELECT
                    CAST(to_char(point.day, 'YYYYMMDD') || point.slot::text AS integer) AS id,
                    point.time AS time,
                    point.position AS position
                FROM daily_ohlc AS point
            )
        """)
