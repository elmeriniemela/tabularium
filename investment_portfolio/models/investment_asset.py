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
from concurrent.futures import ThreadPoolExecutor
import functools
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

    company_ids = fields.Many2many(
        string="Companies",
        comodel_name='res.company',
        default=lambda self: self.env.company,
    )

    last_price_id = fields.Many2one(string='Last Price Record', comodel_name='investment.asset.price')
    last_update = fields.Datetime(related='last_price_id.time', store=True)
    last_price = fields.Monetary(string="Last Price", related='last_price_id.price', store=True, currency_field='currency_id', group_operator=None, inverse='_inverse_last_price')
    expected_yearly_appreciation = fields.Float(group_operator='avg', default=0.0, digits='Investment Asset Interest', tracking=True)
    plausible_ath_drawdown = fields.Float(string="Plausible ATH drawdown", group_operator='avg', default=0.0, digits='Investment Asset Interest', tracking=True)
    ath_price = fields.Monetary(string='ATH Price', currency_field='currency_id', compute='_compute_ath_price', group_operator=None, store=True)
    current_ath_drawdown = fields.Float(string="Current ATH drawdown", compute='_compute_ath_price', group_operator=None, store=True)
    drawdown_price = fields.Monetary(string='Plausible Drawdown Price', currency_field='currency_id', compute='_compute_ath_price', group_operator=None, store=True)

    daily_price_id = fields.Many2one(comodel_name='investment.asset.price')
    weekly_price_id = fields.Many2one(comodel_name='investment.asset.price')
    monthly_price_id = fields.Many2one(comodel_name='investment.asset.price')
    three_month_price_id = fields.Many2one(comodel_name='investment.asset.price')
    six_month_price_id = fields.Many2one(comodel_name='investment.asset.price')
    ytd_price_id = fields.Many2one(comodel_name='investment.asset.price')
    one_year_price_id = fields.Many2one(comodel_name='investment.asset.price')
    three_year_price_id = fields.Many2one(comodel_name='investment.asset.price')
    five_year_price_id = fields.Many2one(comodel_name='investment.asset.price')
    ten_year_price_id = fields.Many2one(comodel_name='investment.asset.price')


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


    @api.depends('split_ids', 'last_price_id', 'plausible_ath_drawdown')
    def _compute_ath_price(self):
        P = self.env['investment.asset.price']
        for asset in self:
            if not asset.ath_price or asset.ath_price < asset.last_price_id.price_adjusted:
                prices = [P.search([
                    ('asset_id', '=', asset.id),
                    ('prediction', '=', False),
                    ('time', '<', asset.split_ids[:1].time or fields.Datetime.now()),
                ], order='price desc', limit=1)]

                for n, split in enumerate(asset.split_ids, start=1):
                    nextsplit = asset.split_ids[n:n+1]
                    prices.append(P.search([
                        ('asset_id', '=', asset.id),
                        ('prediction', '=', False),
                        ('time', '<', nextsplit.time or fields.Datetime.now()),
                        ('time', '>=', split.time),
                    ], order='price desc', limit=1))

                asset.ath_price = max(prices, key=lambda p: p.price_adjusted).price_adjusted
            asset.drawdown_price = (1-asset.plausible_ath_drawdown) * asset.ath_price
            asset.current_ath_drawdown = (asset.ath_price - asset.last_price_id.price_adjusted) / asset.ath_price if asset.ath_price else 0.0


    @api.depends('last_price_id', 'last_price_id.price')
    def _compute_last_price(self):

        def percent_change(closing_price_id, market_price_id):
            closing_price = closing_price_id.price_adjusted or 0.0
            return (market_price_id.price-closing_price)/closing_price if closing_price else 0.0

        for record in self:
            record.daily_price = percent_change(record.daily_price_id, record.last_price_id)
            record.weekly_price = percent_change(record.weekly_price_id, record.last_price_id)
            record.monthly_price = percent_change(record.monthly_price_id, record.last_price_id)
            record.three_month_price = percent_change(record.three_month_price_id, record.last_price_id)
            record.six_month_price = percent_change(record.six_month_price_id, record.last_price_id)
            record.ytd_price = percent_change(record.ytd_price_id, record.last_price_id)
            record.one_year_price = percent_change(record.one_year_price_id, record.last_price_id)
            record.three_year_price = percent_change(record.three_year_price_id, record.last_price_id)
            record.five_year_price = percent_change(record.five_year_price_id, record.last_price_id)
            record.ten_year_price = percent_change(record.ten_year_price_id, record.last_price_id)


    def cron_daily_prices(self):
        self.search([])._compute_daily_prices()

    def action_compute_daily_prices(self):
        self._compute_daily_prices()

    def _compute_daily_prices(self):
        "for performance reasons, this is ran only once a day via cron"
        def latest_before(record, time):
            latest_before_id = record.env['investment.asset.price'].search([
                ('asset_id', '=', record.id),
                ('time', '<', time),
                ('prediction', '=', False),
            ], limit=1)
            # if not latest_before_id:
            #     latest_before_id = record.env['investment.asset.price'].search([
            #         ('asset_id', '=', record.id),
            #         ('prediction', '=', False),
            #     ], limit=1, order='time asc') # oldest possible.
            return latest_before_id

        def earliest_closing_after(record, time):
            "This is how google finance calculates YTD, 1Y, 5Y etc. They basically take the first daily closing price after the date."
            earliest_after_id = record.env['investment.asset.price'].search([
                ('asset_id', '=', record.id),
                ('time', '>', time),
                ('prediction', '=', False),
            ], limit=1, order='time asc')

            if not earliest_after_id:
                return latest_before(record, time)

            earliest_closing_after_id = record.env['investment.asset.price'].search([
                ('asset_id', '=', record.id),
                ('time', '<=', earliest_after_id.time.replace(hour=23, minute=59, second=59)),
                ('prediction', '=', False),
            ], limit=1, order='time desc')
            return earliest_closing_after_id

        for record in self:
            record.last_price_id = record.price_ids[:1]
            record.daily_price_id = latest_before(record, fields.Datetime.now().replace(hour=0, minute=0, second=0))
            record.weekly_price_id = latest_before(record, fields.Datetime.now().replace(hour=0, minute=0, second=0)-relativedelta(weeks=1))
            record.monthly_price_id = latest_before(record, fields.Datetime.now().replace(hour=0, minute=0, second=0)-relativedelta(months=1))
            record.three_month_price_id = latest_before(record, fields.Datetime.now().replace(hour=0, minute=0, second=0)-relativedelta(months=3))
            record.six_month_price_id = latest_before(record, fields.Datetime.now().replace(hour=0, minute=0, second=0)-relativedelta(months=6))
            record.ytd_price_id = earliest_closing_after(record, fields.Datetime.now().replace(day=1, month=1, hour=0, minute=0, second=0))
            record.one_year_price_id = earliest_closing_after(record, fields.Datetime.now().replace(hour=0, minute=0, second=0)-relativedelta(years=1))
            record.three_year_price_id = earliest_closing_after(record, fields.Datetime.now().replace(hour=0, minute=0, second=0)-relativedelta(years=3))
            record.five_year_price_id = earliest_closing_after(record, fields.Datetime.now().replace(hour=0, minute=0, second=0)-relativedelta(years=5))
            record.ten_year_price_id = earliest_closing_after(record, fields.Datetime.now().replace(hour=0, minute=0, second=0)-relativedelta(years=10))

    def _inverse_last_price(self):
        Price = self.env['investment.asset.price']
        for record in self:
            if not record.last_price_id:
                record.last_price_id = Price.create({
                    'asset_id': self.id,
                    'time': datetime.datetime.fromtimestamp(0), # first price should be far in history
                    'price': record.last_price,
                })
            elif record.last_price_id.time.date() != fields.Date.today():
                record.last_price_id = Price.create({
                    'asset_id': self.id,
                    'time': fields.Datetime.now(),
                    'price': record.last_price,
                })
            else:
                record.last_price_id.write({
                    'price': record.last_price,
                    'time': fields.Datetime.now(),
                })


    def _exec_integration(self):
        _logger.info("Run integration on %s", self.mapped('ticker'))
        integration = self.mapped('endpoint_id')
        integration.ensure_one()
        integration.produce({'assets' if integration.multi_record else 'asset': self})

    def run_integration(self):
        Asset = self.browse()
        per_integration = {}
        for asset in self.sudo():
            per_integration[asset.endpoint_id] = per_integration.get(asset.endpoint_id, Asset) + asset

        max_workers = int(self.env['ir.config_parameter'].sudo().get_param('investment_portfolio.integration.threads', '3'))
        for integration, assets in per_integration.items():
            if integration.multi_record:
                assets._exec_integration()
            else:
                if max_workers and len(assets) >= max_workers:
                    _logger.info("Start ThreadPoolExecutor(max_workers=%d)", max_workers)
                    with ThreadPoolExecutor(max_workers=max_workers) as executor:
                        # Map tasks to thread pool
                        executor.map(Asset.thread_run_integration, assets.ids)
                else:
                    for asset in assets: asset._exec_integration()


        _logger.info("Done")

    @api.model
    def thread_run_integration(self, asset_id):
         with self.pool.cursor() as cr:
            self.env.flush_all()
            Asset = self.with_env(self.env(cr=cr))
            asset = Asset.browse(asset_id)
            asset._exec_integration()
            Asset.env.cache.invalidate()


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

        if not self.last_price_id or self.last_price_id.time <= time:
            self.sudo().last_price_id = price_id


