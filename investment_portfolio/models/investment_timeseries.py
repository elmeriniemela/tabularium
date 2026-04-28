# -*- coding: utf-8 -*-

import datetime

from odoo import api, models, fields, _
from odoo.tools import float_is_zero, date_utils
from odoo.fields import Domain
import logging
from dateutil.relativedelta import relativedelta
_logger = logging.getLogger(__name__)

class InvestmentTimeseries(models.Model):
    _name = 'investment.timeseries'
    _description = 'Investment Time Series'
    _rec_name = 'position_id'

    position_id = fields.Many2one(
        string="Position",
        comodel_name='investment.position',
        required=True,
        ondelete='cascade',
        index=True,
    )

    date = fields.Date(
        store=True,
        required=True,
        index=True,
    )

    price_id = fields.Many2one(
        string='Closing price',
        comodel_name='investment.asset.price',
        store=True,
        required=True,
        ondelete='cascade',
        index=True,
    )

    position = fields.Monetary(
        string='Closing position',
        compute='_compute_timeseries_aggregate',
        store=True,
        currency_field='company_currency_id',
    )

    profit = fields.Monetary(
        string='Closing profit',
        compute='_compute_timeseries_aggregate',
        store=True,
        currency_field='company_currency_id',
        aggregator='sum'
    )

    open_price_id = fields.Many2one(
        string='Opening price',
        comodel_name='investment.asset.price',
        store=True,
        required=True,
        ondelete='cascade',
        index=True,
    )

    open_position = fields.Monetary(
        string='Opening position',
        compute='_compute_timeseries_aggregate',
        store=True,
        currency_field='company_currency_id',
        aggregator='avg',
    )

    open_profit = fields.Monetary(
        string='Opening profit',
        compute='_compute_timeseries_aggregate',
        store=True,
        currency_field='company_currency_id',
        aggregator='avg',
    )

    high_price_id = fields.Many2one(
        string='High price',
        comodel_name='investment.asset.price',
        store=True,
        required=True,
        ondelete='cascade',
        index=True,
    )

    high_position = fields.Monetary(
        string='High position',
        compute='_compute_timeseries_aggregate',
        store=True,
        currency_field='company_currency_id',
        aggregator='avg',
    )

    high_profit = fields.Monetary(
        string='High profit',
        compute='_compute_timeseries_aggregate',
        store=True,
        currency_field='company_currency_id',
        aggregator='avg',
    )


    low_price_id = fields.Many2one(
        string='Low price',
        comodel_name='investment.asset.price',
        store=True,
        required=True,
        ondelete='cascade',
        index=True,
    )

    low_position = fields.Monetary(
        string='Low position',
        compute='_compute_timeseries_aggregate',
        store=True,
        currency_field='company_currency_id',
        aggregator='avg',
    )

    low_profit = fields.Monetary(
        string='Low profit',
        compute='_compute_timeseries_aggregate',
        store=True,
        currency_field='company_currency_id',
        aggregator='avg',
    )

    quantity = fields.Float(
        compute='_compute_timeseries_aggregate',
        store=True,
        digits='Investment Asset quantity',
    )

    last_price_own_currency = fields.Monetary(
        compute='_compute_timeseries_aggregate',
        store=True,
        currency_field='company_currency_id',
    )

    profit_percent = fields.Float(
        compute='_compute_timeseries_aggregate',
        store=True,
        aggregator='avg',
    )

    transaction_ids = fields.Many2many(
        comodel_name='investment.position.transaction',
        compute='_compute_timeseries_aggregate',
        store=True,
    )

    prediction = fields.Boolean(
        string="Future Price",
        related='price_id.prediction',
        store=True,
        readonly=True,
        index=True,
    )

    interpolated = fields.Boolean(
        string="Interpolated Price",
        related='price_id.interpolated',
    )

    company_currency_id = fields.Many2one(
        related='position_id.company_currency_id',
    )

    company_id = fields.Many2one(
        related='position_id.company_id',
        store=True,
        readonly=True,
        index=True,
    )

    category_id = fields.Many2one(
        related='position_id.asset_id.category_id',
        store=True,
        readonly=True,
        index=True,
    )

    portfolio_id = fields.Many2one(
        related='position_id.portfolio_id',
        store=True,
        readonly=True,
        index=True,
    )

    liquid = fields.Boolean(
        related='category_id.liquid',
        store=True,
        readonly=True,
        index=True,
    )

    granularity = fields.Selection(
        selection=[
            ('1_yearly', 'Yearly'),
            ('2_quaterly', 'Quarterly'),
            ('3_monthly', 'Monthly'),
            ('4_daily', 'Daily'),
        ],
        compute='_compute_granularity',
        store=True,
        index=True,
    )

    is_sunday = fields.Boolean(
        compute='_compute_granularity',
        store=True,
        index=True,
    )

    _date_timeseries_unique = models.Constraint('unique(date, position_id)', 'This timeseries already exists!')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            missing_ohlc = {'open_price_id', 'high_price_id', 'low_price_id'} - vals.keys()
            if missing_ohlc:
                price_id = vals['price_id']
                vals.setdefault('open_price_id', price_id)
                vals.setdefault('high_price_id', price_id)
                vals.setdefault('low_price_id', price_id)
        return super().create(vals_list)

    @api.depends('date')
    def _compute_granularity(self):
        for record in self:
            if date_utils.end_of(record.date, "year") == record.date:
                record.granularity = '1_yearly'
            elif date_utils.end_of(record.date, "quarter") == record.date:
                record.granularity = '2_quaterly'
            elif date_utils.end_of(record.date, "month") == record.date:
                record.granularity = '3_monthly'
            else:
                record.granularity = '4_daily'

            record.is_sunday = record.date.isoweekday() == 7


    @api.model
    def formatted_read_group(self, domain, groupby=(), aggregates=(), having=(), offset=0, limit=None, order=None) -> list[dict]:
        """
        Returns the result of a read_group and the total number of groups matching the search domain.

        :param domain: search domain
        :param groupby: list of fields to group on (see ``groupby``` param of ``read_group``)
        :param aggregates: list of aggregates to compute
        :param limit: see ``limit`` param of ``formatted_read_group``
        :param offset: see ``offset`` param of ``formatted_read_group``
        :param order: see ``order`` param of ``formatted_read_group``
        :return: {
            'groups': array of read groups
            'length': total number of groups
        }
        """
        if not any(c[0] in ('granularity', 'is_sunday') for c in domain):
            map_group = {
                'day': [('granularity', 'in', ['4_daily', '3_monthly', '2_quaterly', '1_yearly'])],
                'week': [('is_sunday', '=', True)],
                'month': [('granularity', 'in', ['3_monthly', '2_quaterly', '1_yearly'])],
                'quarter': [('granularity', 'in', ['2_quaterly', '1_yearly'])],
                'year': [('granularity', 'in', ['1_yearly'])],
            }
            for group in groupby:
                match = 'date:'
                if group.startswith(match):
                    add_domain = map_group[group[len(match):]]
                    domain = Domain.AND([domain, add_domain])
                    _logger.info("Additional domain: %s", add_domain)
                    break

        return super().formatted_read_group(domain, groupby, aggregates, having, offset, limit, order)


    def refresh_price(self):
        today = datetime.date.today()
        for serie in self:
            if serie.date == today:
                serie.price_id = self.env['investment.asset.price'].search([
                    ('prediction', '=', False),
                    ('asset_id', '=', serie.position_id.asset_id.id),
                ], limit=1, order='time desc') # update the latest price when not doing predictions.

    @api.model
    def _get_daily_price_extremes(self, asset_ids):
        Price = self.env['investment.asset.price']
        if not asset_ids:
            return {}, {}

        self.env.cr.execute(
            """
            WITH ranked_prices AS (
                SELECT
                    id,
                    asset_id,
                    DATE(time) AS day,
                    ROW_NUMBER() OVER (
                        PARTITION BY asset_id, DATE(time)
                        ORDER BY time ASC, id ASC
                    ) AS open_rank,
                    ROW_NUMBER() OVER (
                        PARTITION BY asset_id, DATE(time)
                        ORDER BY price DESC, time ASC, id ASC
                    ) AS high_rank,
                    ROW_NUMBER() OVER (
                        PARTITION BY asset_id, DATE(time)
                        ORDER BY price ASC, time ASC, id ASC
                    ) AS low_rank
                FROM investment_asset_price
                WHERE asset_id IN %s
                  AND prediction IS NOT TRUE
            )
            SELECT
                asset_id,
                day,
                MAX(CASE WHEN open_rank = 1 THEN id END) AS open_price_id,
                MAX(CASE WHEN high_rank = 1 THEN id END) AS high_price_id,
                MAX(CASE WHEN low_rank = 1 THEN id END) AS low_price_id
            FROM ranked_prices
            GROUP BY asset_id, day
            """,
            (tuple(asset_ids),),
        )

        day_prices = {}
        price_ids = set()
        for asset_id, day, open_price_id, high_price_id, low_price_id in self.env.cr.fetchall():
            if isinstance(day, datetime.datetime):
                day = day.date()
            day_prices[(asset_id, day)] = (open_price_id, high_price_id, low_price_id)
            price_ids.add(open_price_id)
            price_ids.add(high_price_id)
            price_ids.add(low_price_id)

        prices = {price.id: price for price in Price.browse(list(price_ids))}
        return day_prices, prices

    @api.depends('position_id', 'date')
    def _compute_timeseries_aggregate(self):
        _logger.info(f"Compute time series aggregate on {self.mapped('position_id.name')} for {len(self)} records.")
        Transaction = self.env['investment.position.transaction'].browse()
        transactions = Transaction.search([
            ('position_id', 'in', self.mapped('position_id').ids),
            ('usage', 'in', ('record', 'prediction')),
        ])
        trans_map = {}
        for trans in transactions:
            trans_map[trans.position_id] = trans_map.get(trans.position_id, Transaction) + trans

        day_prices, price_map = self._get_daily_price_extremes(self.mapped('position_id.asset_id').ids)

        for record in self:
            if not record.position_id:
                continue

            def set_ohlc_values(prefix, price_id):
                vals = record.position_id._get_position(
                    record.convert_currency(price_id),
                    record.transaction_ids,
                )
                record[f'{prefix}_price_id'] = price_id
                record[f'{prefix}_position'] = vals['position']
                record[f'{prefix}_profit'] = vals['profit']

            time_cutoff = datetime.datetime(record.date.year, record.date.month, record.date.day, 23, 59, 0)
            record.transaction_ids = trans_map.get(record.position_id, Transaction).filtered(lambda t: t.time <= time_cutoff) # latest but before date

            record.last_price_own_currency = record.convert_currency(record.price_id)

            vals = record.position_id._get_position(record.last_price_own_currency, record.transaction_ids).items()
            vals = {k: v for k, v in vals if k in record._fields}
            assert vals, "Filtering with record._fields failed."
            record.update(vals)

            ohlc_ids = day_prices.get((record.position_id.asset_id.id, record.date))
            if ohlc_ids:
                open_price_id, high_price_id, low_price_id = (
                    price_map[ohlc_ids[0]],
                    price_map[ohlc_ids[1]],
                    price_map[ohlc_ids[2]],
                )
            else:
                open_price_id = high_price_id = low_price_id = record.price_id

            set_ohlc_values('open', open_price_id)
            set_ohlc_values('high', high_price_id)
            set_ohlc_values('low', low_price_id)


    def convert_currency(self, price_id):
        self.ensure_one()
        return self.position_id.asset_id.currency_id._convert(
            from_amount=price_id.price,
            to_currency=self.company_currency_id,
            company=self.company_id,
            date=self.date,
        )
