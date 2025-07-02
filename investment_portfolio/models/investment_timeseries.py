# -*- coding: utf-8 -*-

import datetime

from odoo import api, models, fields, _
from odoo.tools import float_is_zero, date_utils
from odoo.osv import expression
import logging
from dateutil.relativedelta import relativedelta


_logger = logging.getLogger(__name__)

class InvestmentTimeseries(models.Model):
    _name = 'investment.timeseries'
    _description = 'Investment Time Series'
    _rec_name = 'position_id'

    position = fields.Monetary(compute='_compute_timeseries_aggregate', store=True, currency_field='company_currency_id')
    quantity = fields.Float(compute='_compute_timeseries_aggregate', store=True, digits='Investment Asset quantity')

    last_price_own_currency = fields.Monetary(compute='_compute_timeseries_aggregate', store=True, currency_field='company_currency_id')
    profit = fields.Monetary(compute='_compute_timeseries_aggregate', store=True, currency_field='company_currency_id', aggregator='sum')
    profit_percent = fields.Float(compute='_compute_timeseries_aggregate', store=True, aggregator='avg')
    transaction_ids = fields.Many2many(comodel_name='investment.position.transaction', compute='_compute_timeseries_aggregate', store=True)
    price_id = fields.Many2one(
        comodel_name='investment.asset.price',
        store=True,
        required=True,
        ondelete='cascade',
        index=True,
    )

    prediction = fields.Boolean(
        string="Future Price",
        related='price_id.prediction',
    )

    interpolated = fields.Boolean(
        string="Interpolated Price",
        related='price_id.interpolated',
    )

    date = fields.Date(
        store=True,
        required=True,
        index=True,
    )


    company_currency_id = fields.Many2one(related='position_id.company_currency_id')
    company_id = fields.Many2one(related='position_id.company_id')


    position_id = fields.Many2one(
        string="Asset",
        comodel_name='investment.position',
        required=True,
        ondelete='cascade',
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

    _sql_constraints = [
        ('date_timeseries_unique', 'unique(date, position_id)', 'This timeseries already exists!'),
    ]

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
    def web_read_group(self, domain, fields, groupby, limit=None, offset=0, orderby=False, lazy=True):
        """
        Returns the result of a read_group and the total number of groups matching the search domain.

        :param domain: search domain
        :param fields: list of fields to read (see ``fields``` param of ``read_group``)
        :param groupby: list of fields to group on (see ``groupby``` param of ``read_group``)
        :param limit: see ``limit`` param of ``read_group``
        :param offset: see ``offset`` param of ``read_group``
        :param orderby: see ``orderby`` param of ``read_group``
        :param lazy: see ``lazy`` param of ``read_group``
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
                    domain = expression.AND([domain, add_domain])
                    _logger.info("Additional domain: %s", add_domain)
                    break

        return super().web_read_group(domain, fields, groupby, limit=limit, offset=offset, orderby=orderby, lazy=lazy)


    @api.depends('position_id', 'date')
    def _compute_timeseries_aggregate(self):
        _logger.info(f"Compute time series aggregate on {self.mapped('position_id.name')} for {len(self)} records.")
        for record in self:
            if not record.position_id:
                continue

            time_cutoff = datetime.datetime(record.date.year, record.date.month, record.date.day, 23, 59, 0)
            record.transaction_ids = record.env['investment.position.transaction'].search([
                ('time', '<=', time_cutoff),
                ('position_id', '=', record.position_id.id),
                ('usage', 'in', ('record', 'prediction')),
            ]) # latest but before date

            record.last_price_own_currency = record.price_id.currency_id._convert(
                from_amount=record.price_id.price,
                to_currency=record.company_currency_id,
                company=record.company_id,
                date=record.price_id.time or fields.Datetime.now(),
            )

            vals = record.position_id._get_position(record.last_price_own_currency, record.transaction_ids).items()
            vals = {k: v for k, v in vals if k in record._fields}
            assert vals, "Filtering with record._fields failed."
            record.update(vals)


