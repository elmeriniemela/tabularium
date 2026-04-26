# -*- coding: utf-8 -*-

from odoo import fields, models, tools, _


class InvestmentTotalTimeseries(models.Model):
    _name = 'investment.total.timeseries'
    _description = 'Investment Total Time Series'
    _auto = False
    _rec_name = 'time'
    _order = 'time desc, id desc'

    company_id = fields.Many2one(
        comodel_name='res.company',
        readonly=True,
    )
    time = fields.Datetime(readonly=True)
    tstype = fields.Selection(
        selection=[
            ('open', 'Open'),
            ('high', 'High'),
            ('low', 'Low'),
            ('close', 'Close'),
        ]
    )
    position = fields.Float(
        readonly=True,
        aggregator='avg',
    )

    ts_list = fields.Json()
    timeseries_ids = fields.Many2many(
        comodel_name='investment.timeseries',
        compute='_compute_timeseries_ids',
    )

    def action_view_timeseries(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Investment Timeseries'),
            'res_model': 'investment.timeseries',
            'view_mode': 'list',
            'views': [[False, 'list'], [False, 'form']],
            'domain': [('id', 'in', self.mapped('timeseries_ids').ids)],
        }

    def _compute_timeseries_ids(self):
        for record in self:
            record.timeseries_ids = record.ts_list

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        # Portfolio OHLC rows are daily aggregates, so the view assigns
        # deterministic in-day timestamps instead of reusing per-position times.
        self.env.cr.execute(f"""
            CREATE OR REPLACE VIEW {self._table} AS (
                WITH daily_totals AS (
                    SELECT
                        ts.company_id,
                        ts.date,
                        array_agg(ts.id) AS ts_list,
                        SUM(ts.open_position) AS open_position,
                        SUM(ts.high_position) AS high_position,
                        SUM(ts.low_position) AS low_position,
                        SUM(ts.position) AS close_position
                    FROM investment_timeseries ts
                    WHERE ts.liquid = TRUE
                    AND ts.prediction IS NOT TRUE
                    GROUP BY ts.company_id, ts.date
                ),
                ohlc_lines AS (
                    SELECT
                        dt.company_id,
                        dt.open_position AS position,
                        'open' AS tstype,
                        dt.ts_list,
                        dt.date::timestamp AS time
                    FROM daily_totals dt

                    UNION ALL

                    SELECT
                        dt.company_id,
                        dt.high_position AS position,
                        'high' AS tstype,
                        dt.ts_list,
                        dt.date::timestamp + INTERVAL '1 minute' AS time
                    FROM daily_totals dt

                    UNION ALL

                    SELECT
                        dt.company_id,
                        dt.low_position AS position,
                        'low' AS tstype,
                        dt.ts_list,
                        dt.date::timestamp + INTERVAL '2 minute' AS time
                    FROM daily_totals dt

                    UNION ALL

                    SELECT
                        dt.company_id,
                        dt.close_position AS position,
                        'close' AS tstype,
                        dt.ts_list,
                        dt.date::timestamp + INTERVAL '3 minute' AS time
                    FROM daily_totals dt
                )

                SELECT
                    ROW_NUMBER() OVER (ORDER BY ol.company_id, ol.time)::integer AS id,
                    ol.company_id,
                    ol.position,
                    ol.tstype,
                    ol.ts_list,
                    ol.time
                FROM ohlc_lines ol
            )
        """)
