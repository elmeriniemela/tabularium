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
        tools.drop_view_if_exists(self.env.cr, self._table)
        # Portfolio OHLC rows are daily aggregates, so the view assigns
        # deterministic in-day timestamps instead of reusing per-position times.
        self.env.cr.execute(f"""
            CREATE OR REPLACE VIEW {self._table} AS (
                WITH daily_totals AS (
                    SELECT
                        ts.date,
                        SUM(ts.open_position) AS open_position,
                        SUM(ts.high_position) AS high_position,
                        SUM(ts.low_position) AS low_position,
                        SUM(ts.position) AS close_position
                    FROM investment_timeseries ts
                    WHERE ts.company_id = 1
                    AND ts.liquid = TRUE
                    AND ts.prediction IS NOT TRUE
                    GROUP BY ts.date
                )
                (
                SELECT
                    CAST(TO_CHAR(dt.date, 'YYYYMMDD') AS INTEGER) * 10 + 1 AS id,
                    dt.open_position AS position,
                    dt.date::timestamp AS time
                FROM daily_totals dt
                )

                UNION ALL

                (
                SELECT
                    CAST(TO_CHAR(dt.date, 'YYYYMMDD') AS INTEGER) * 10 + 2 AS id,
                    dt.high_position AS position,
                    dt.date::timestamp + INTERVAL '1 second' AS time
                FROM daily_totals dt
                )

                UNION ALL

                (
                SELECT
                    CAST(TO_CHAR(dt.date, 'YYYYMMDD') AS INTEGER) * 10 + 3 AS id,
                    dt.low_position AS position,
                    dt.date::timestamp + INTERVAL '2 second' AS time
                FROM daily_totals dt
                )

                UNION ALL

                (
                SELECT
                    CAST(TO_CHAR(dt.date, 'YYYYMMDD') AS INTEGER) * 10 + 4 AS id,
                    dt.close_position AS position,
                    dt.date::timestamp + INTERVAL '3 second' AS time
                FROM daily_totals dt
                )
            )
        """)
