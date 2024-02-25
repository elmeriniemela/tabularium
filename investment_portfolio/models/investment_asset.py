# -*- coding: utf-8 -*-

from odoo import api, models, fields, _
from odoo.exceptions import ValidationError
from odoo.tools import float_is_zero, float_compare
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
    _order = 'portfolio_id, sequence, id'

    sequence = fields.Integer(string='Sequence')

    name = fields.Char(required=True)

    active = fields.Boolean(default=True)

    ticker = fields.Char(required=True)

    category_id = fields.Many2one(
        comodel_name='investment.category',
        required=True,
        index=True,
    )

    liquid = fields.Boolean(related='category_id.liquid', store=True, readonly=True)

    currency_id = fields.Many2one(
        comodel_name='res.currency',
        required=True,
        index=True,
    )

    price_ids = fields.One2many(
        comodel_name='investment.asset.price',
        inverse_name='asset_id',
        domain=[('prediction', '=', False)],
    )

    last_price_id = fields.Many2one(
        string='Last Price Record',
        comodel_name='investment.asset.price',
        compute='_compute_aggregate', store=True)
    last_update = fields.Datetime(related='last_price_id.time', store=True)
    last_price_currency = fields.Monetary(string="Last Price", related='last_price_id.price', store=True, currency_field='currency_id', group_operator=None)


    daily_price = fields.Float(compute='_compute_aggregate', store=True, group_operator='avg', string="1 Day")
    weekly_price = fields.Float(compute='_compute_aggregate', store=True, group_operator='avg', string="1 Week")
    monthly_price = fields.Float(compute='_compute_aggregate', store=True, group_operator='avg', string="1 Month")
    three_month_price = fields.Float(compute='_compute_aggregate', store=True, group_operator='avg', string="3 Months")
    six_month_price = fields.Float(compute='_compute_aggregate', store=True, group_operator='avg', string="6 Months")
    ytd_price = fields.Float(compute='_compute_aggregate', store=True, group_operator='avg', string="YTD")
    one_year_price = fields.Float(compute='_compute_aggregate', store=True, group_operator='avg', string="1 Year")
    three_year_price = fields.Float(compute='_compute_aggregate', store=True, group_operator='avg', string="3 Year")
    five_year_price = fields.Float(compute='_compute_aggregate', store=True, group_operator='avg', string="5 Year")


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

    @api.depends(
        'price_ids',
        'price_ids.price',
    )
    def _compute_aggregate(self):

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

            closing_price = closing_price_id.price or 0.0
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


    def run_integration(self):
        for asset in self:
            asset.endpoint_id.produce({'asset': asset})
            asset._compute_aggregate() # For some reason, the depends on price_ids does not work...


    def price_upsert(self, time, price):
        "Used by investment integrations."
        self.ensure_one()
        Price = self.env['investment.asset.price']
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


