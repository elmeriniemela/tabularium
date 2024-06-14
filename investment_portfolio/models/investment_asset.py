# -*- coding: utf-8 -*-

from odoo import api, models, fields, _
from odoo.exceptions import ValidationError
from odoo.tools import float_is_zero, float_compare, date_utils
import traceback
from dateutil.relativedelta import relativedelta
from dateutil import rrule
import pytz
import datetime
import logging

_logger = logging.getLogger(__name__)


class InvestmentAsset(models.Model):
    _name = 'investment.asset'
    _description = 'Investment Asset'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'sequence, id'
    _rec_name = 'ticker'

    sequence = fields.Integer(string='Sequence')

    active = fields.Boolean(default=True)

    ticker = fields.Char(required=True, string="Ticker / ID")

    category_id = fields.Many2one(
        comodel_name='investment.category',
        required=True,
        index=True,
        default=lambda self: self.env['investment.category'].search([], limit=1)
    )

    liquid = fields.Boolean(related='category_id.liquid', store=True, readonly=True)

    currency_id = fields.Many2one(
        comodel_name='res.currency',
        required=True,
        index=True,
        default=lambda self: self.env.company.currency_id,
    )

    price_ids = fields.One2many(
        comodel_name='investment.asset.price',
        inverse_name='asset_id',
        domain=[('prediction', '=', False)],
    )

    split_ids = fields.One2many(
        comodel_name='investment.asset.split',
        inverse_name='asset_id',
    )

    owner_ids = fields.Many2many(
        comodel_name='res.users',
        default=lambda self: self.env.user,
    )

    last_price_id = fields.Many2one(
        string='Last Price Record',
        comodel_name='investment.asset.price',
        compute='_compute_last_price', store=True)
    last_update = fields.Datetime(related='last_price_id.time', store=True)
    last_price = fields.Monetary(string="Last Price", related='last_price_id.price', store=True, currency_field='currency_id', group_operator=None, inverse='_inverse_last_price')
    expected_yearly_appreciation = fields.Float(group_operator='avg', default=0.0, digits='Investment Asset Interest', tracking=True)


    daily_price = fields.Float(compute='_compute_last_price', store=True, group_operator='avg', string="1 Day")
    weekly_price = fields.Float(compute='_compute_last_price', store=True, group_operator='avg', string="1 Week")
    monthly_price = fields.Float(compute='_compute_last_price', store=True, group_operator='avg', string="1 Month")
    three_month_price = fields.Float(compute='_compute_last_price', store=True, group_operator='avg', string="3 Months")
    six_month_price = fields.Float(compute='_compute_last_price', store=True, group_operator='avg', string="6 Months")
    ytd_price = fields.Float(compute='_compute_last_price', store=True, group_operator='avg', string="YTD")
    one_year_price = fields.Float(compute='_compute_last_price', store=True, group_operator='avg', string="1 Year")
    three_year_price = fields.Float(compute='_compute_last_price', store=True, group_operator='avg', string="3 Years")
    five_year_price = fields.Float(compute='_compute_last_price', store=True, group_operator='avg', string="5 Years")
    ten_year_price = fields.Float(compute='_compute_last_price', store=True, group_operator='avg', string="10 Years")


    endpoint_id = fields.Many2one(
        string="Integration",
        comodel_name='api.endpoint',
        index=True,
        ondelete='restrict',
        domain=[
            ('usage_field_id.name', '=', 'endpoint_id'),
            ('usage_field_id.model_id.model', '=', 'investment.asset'),
        ],
    )

    @api.onchange('expected_yearly_appreciation')
    def invalidate_predicted_prices(self):
        self.env['investment.asset.price'].search([
            ('asset_id', '=', self.id),
            ('prediction', '=', True),
        ]).unlink()


    def price_at_date(self, date):
        self.ensure_one()
        time_cutoff = datetime.datetime(date.year, date.month, date.day, 0, 0, 0) # This has to be the end of day.
        err_msg = "No price for %s at %s." % (self.ticker, time_cutoff)
        at_price_id = self.env['investment.asset.price'].search([
                ('time', '<=', date_utils.end_of(time_cutoff, "day")),
                ('time', '>=', date_utils.start_of(time_cutoff, "day")),
                ('asset_id', '=', self.id),
                ('prediction', '=', date > fields.Date.today()),
            ], limit=1, order='time desc') # latest = closing price for the day

        if not at_price_id:
            # This time allow predictions.
            at_price_id = self.env['investment.asset.price'].search([
                ('time', '<=', date_utils.end_of(time_cutoff, "day")),
                ('time', '>=', date_utils.start_of(time_cutoff, "day")),
                ('asset_id', '=', self.id),
            ], limit=1, order='time desc') # latest = closing price for the day

        if not at_price_id:
            after_price_id = self.env['investment.asset.price'].search([
                    ('time', '>', time_cutoff),
                    ('asset_id', '=', self.id),
                ], limit=1, order='time asc') # earliest but after time_cutoff
            before_price_id = self.env['investment.asset.price'].search([
                    ('time', '<=', time_cutoff),
                    ('asset_id', '=', self.id),
                ], limit=1, order='time desc') # latest but before time_cutoff
            if before_price_id and after_price_id:
                slope = (after_price_id.price - before_price_id.price) / (after_price_id.time - before_price_id.time).days
                interpolated_price = before_price_id.price + slope*(time_cutoff-before_price_id.time).days
                at_price_id = self.env['investment.asset.price'].create({
                    'time': time_cutoff,
                    'asset_id': self.id,
                    'prediction': after_price_id.prediction or before_price_id.prediction,
                    'interpolated': True,
                    'price': interpolated_price,
                })
            elif before_price_id:
                days = (date - before_price_id.time.date()).days
                predicted_price = before_price_id.price * (1+self.expected_yearly_appreciation)**(days/365)
                at_price_id = self.env['investment.asset.price'].create({
                    'time': time_cutoff,
                    'asset_id': self.id,
                    'prediction': True,
                    'price': predicted_price,
                })
            # DO we want to "predict" old prices?
            # elif after_price_id:
            #     days = (date - after_price_id.time.date()).days
            #     predicted_price = after_price_id.price * (1+self.expected_yearly_appreciation)**(days/365)
            #     at_price_id = self.env['investment.asset.price'].create({
            #         'time': time_cutoff,
            #         'asset_id': self.id,
            #         'prediction': True,
            #         'price': predicted_price,
            #     })

            else:
                raise RuntimeError(err_msg)

        assert at_price_id, err_msg
        return at_price_id


    @api.depends(
        'price_ids',
        'price_ids.price',
    )
    def _compute_last_price(self):

        def percent_change(record, time, market_price):
            closing_price_id = record.env['investment.asset.price'].search([
                ('asset_id', '=', record.id),
                ('time', '<', time),
                ('prediction', '=', False),
            ], limit=1)
            if not closing_price_id:
                closing_price_id = record.env['investment.asset.price'].search([
                    ('asset_id', '=', record.id),
                    ('prediction', '=', False),
                ], limit=1, order='time asc') # oldest possible.

            closing_price = closing_price_id.price_adjusted or 0.0
            return (market_price-closing_price)/closing_price if closing_price else 0.0



        for record in self:
            record.last_price_id = record.price_ids[:1]
            record.daily_price = percent_change(record, fields.Datetime.now().replace(hour=0, minute=0, second=0), record.last_price_id.price)
            record.weekly_price = percent_change(record, fields.Datetime.now().replace(hour=0, minute=0, second=0)-relativedelta(weeks=1), record.last_price_id.price)
            record.monthly_price = percent_change(record, fields.Datetime.now().replace(hour=0, minute=0, second=0)-relativedelta(months=1), record.last_price_id.price)
            record.three_month_price = percent_change(record, fields.Datetime.now().replace(hour=0, minute=0, second=0)-relativedelta(months=3), record.last_price_id.price)
            record.six_month_price = percent_change(record, fields.Datetime.now().replace(hour=0, minute=0, second=0)-relativedelta(months=6), record.last_price_id.price)
            record.ytd_price = percent_change(record, fields.Datetime.now().replace(day=1, month=1, hour=0, minute=0, second=0), record.last_price_id.price)
            record.one_year_price = percent_change(record, fields.Datetime.now().replace(hour=0, minute=0, second=0)-relativedelta(years=1), record.last_price_id.price)
            record.three_year_price = percent_change(record, fields.Datetime.now().replace(hour=0, minute=0, second=0)-relativedelta(years=3), record.last_price_id.price)
            record.five_year_price = percent_change(record, fields.Datetime.now().replace(hour=0, minute=0, second=0)-relativedelta(years=5), record.last_price_id.price)
            record.ten_year_price = percent_change(record, fields.Datetime.now().replace(hour=0, minute=0, second=0)-relativedelta(years=10), record.last_price_id.price)


    def _inverse_last_price(self):
        Price = self.env['investment.asset.price']
        for record in self:
            if not record.last_price_id:
                record.last_price_id = Price.create({
                    'asset_id': self.id,
                    'time': datetime.datetime.fromtimestamp(0),
                    'price': record.last_price,
                })
            else:
                record.last_price_id.price = record.last_price

    def run_integration(self):
        for asset in self.sudo():
            asset.endpoint_id.produce({'asset': asset})
            asset._compute_last_price() # For some reason, the depends on price_ids does not work...


    def price_upsert(self, time, price):
        "Used by investment integrations."
        self.ensure_one()
        Price = self.env['investment.asset.price'].sudo()
        time = time.astimezone(pytz.utc).replace(tzinfo=None)
        price_id = Price.search([
            ('asset_id', '=', self.id),
            ('time', '=', time),
        ], limit=1)
        if price_id:
            price_id.price = price
        else:
            price_id = Price.create({
                'asset_id': self.id,
                'time': time,
                'price': price,
            })
        return price_id


