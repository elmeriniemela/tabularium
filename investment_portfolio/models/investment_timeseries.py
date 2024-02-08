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
    _rec_name = 'asset_id'

    position = fields.Monetary(compute='_compute_aggregate', store=True, currency_field='company_currency_id')
    quantity = fields.Float(compute='_compute_aggregate', store=True, digits='Investment Asset quantity')

    position = fields.Monetary(compute='_compute_aggregate', store=True, currency_field='company_currency_id')

    cost_basis = fields.Monetary(compute='_compute_aggregate', store=True, currency_field='company_currency_id')


    last_price = fields.Monetary(compute='_compute_aggregate', store=True, currency_field='company_currency_id')
    profit = fields.Monetary(compute='_compute_aggregate', store=True, currency_field='company_currency_id', group_operator='sum')
    profit_percent = fields.Float(compute='_compute_aggregate', store=True, group_operator='avg')
    transaction_ids = fields.Many2many(comodel_name='investment.asset.transaction', compute='_compute_aggregate', store=True)
    price_id = fields.Many2one(
        comodel_name='investment.asset.price',
        compute='_compute_aggregate',
        store=True,
        ondelete='cascade',
        index=True,
    )

    prediction = fields.Boolean(
        string="Price Interpolated",
        related='price_id.prediction',
    )

    date = fields.Date(
        store=True,
        required=True,
        index=True,
    )


    company_currency_id = fields.Many2one(related='asset_id.company_currency_id', string="Company Currency")


    asset_id = fields.Many2one(
        comodel_name='investment.asset',
        required=True,
        ondelete='cascade',
        index=True,
    )

    category_id = fields.Many2one(
        related='asset_id.category_id',
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
            ('2_quaterly', 'Quaterly'),
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
        ('date_position_unique', 'unique(date, asset_id)', 'This position already exists!'),
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
    def web_read_group(self, domain, fields, groupby, limit=None, offset=0, orderby=False,
                       lazy=True, expand=False, expand_limit=None, expand_orderby=False):
        """
        Returns the result of a read_group (and optionally search for and read records inside each
        group), and the total number of groups matching the search domain.

        :param domain: search domain
        :param fields: list of fields to read (see ``fields``` param of ``read_group``)
        :param groupby: list of fields to group on (see ``groupby``` param of ``read_group``)
        :param limit: see ``limit`` param of ``read_group``
        :param offset: see ``offset`` param of ``read_group``
        :param orderby: see ``orderby`` param of ``read_group``
        :param lazy: see ``lazy`` param of ``read_group``
        :param expand: if true, and groupby only contains one field, read records inside each group
        :param expand_limit: maximum number of records to read in each group
        :param expand_orderby: order to apply when reading records in each group
        :return: {
            'groups': array of read groups
            'length': total number of groups
        }
        """
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
                domain = expression.AND([domain, map_group[group[len(match):]]])
                break

        return super().web_read_group(domain, fields, groupby, limit=limit, offset=offset, orderby=orderby,
                       lazy=lazy, expand=expand, expand_limit=expand_limit, expand_orderby=expand_orderby)


    @api.depends('asset_id', 'date')
    def _compute_aggregate(self):
        _logger.info(f"Compute time series aggregate on {self.mapped('asset_id.name')} for {len(self)} records.")
        for record in self:
            if not record.asset_id:
                continue

            t = record.date
            time_cutoff = datetime.datetime(t.year, t.month, t.day, 0, 0, 0) # This has to be the end of day.
            record.transaction_ids = record.env['investment.asset.transaction'].search([
                ('time', '<=', time_cutoff),
                ('asset_id', '=', record.asset_id.id),
                ('usage', 'in', ('record', 'prediction')),
            ]) # latest but before date

            # Determine the best estimate for market price at 'record.date'.
            at_price_id = record.env['investment.asset.price'].search([
                    ('time', '<=', date_utils.end_of(time_cutoff, "day")),
                    ('time', '>=', date_utils.start_of(time_cutoff, "day")),
                    ('asset_id', '=', record.asset_id.id),
                    ('prediction', '=', record.date > fields.Date.today()),
                ], limit=1, order='time desc') # latest = closing price for the day

            if not at_price_id:
                # This time allow predictions.
                at_price_id = record.env['investment.asset.price'].search([
                    ('time', '<=', date_utils.end_of(time_cutoff, "day")),
                    ('time', '>=', date_utils.start_of(time_cutoff, "day")),
                    ('asset_id', '=', record.asset_id.id),
                ], limit=1, order='time desc') # latest = closing price for the day

            if not at_price_id:
                after_price_id = record.env['investment.asset.price'].search([
                        ('time', '>', time_cutoff),
                        ('asset_id', '=', record.asset_id.id),
                    ], limit=1, order='time asc') # earliest but after time_cutoff
                before_price_id = record.env['investment.asset.price'].search([
                        ('time', '<=', time_cutoff),
                        ('asset_id', '=', record.asset_id.id),
                    ], limit=1, order='time desc') # latest but before time_cutoff
                if before_price_id and after_price_id:
                    slope = (after_price_id.price - before_price_id.price) / (after_price_id.time - before_price_id.time).days
                    interpolated_price = before_price_id.price + slope*(time_cutoff-before_price_id.time).days
                    at_price_id = record.env['investment.asset.price'].create({
                        'time': time_cutoff,
                        'asset_id': record.asset_id.id,
                        'prediction': True,
                        'price': interpolated_price,
                    })
                else:
                    _logger.warning("No price for %s at %s.", record.asset_id.name, time_cutoff)


            record.price_id = at_price_id
            record.last_price = record.price_id.currency_id._convert(
                from_amount=record.price_id.price,
                to_currency=self.company_currency_id,
                company=self.env.company,
                date=record.price_id.time or fields.Datetime.now(),
            )

            vals = record.asset_id._get_position(record.last_price, record.transaction_ids).items()
            vals = {k: v for k, v in vals if k in record._fields}
            assert vals, "Filtering with record._fields failed."
            record.update(vals)


