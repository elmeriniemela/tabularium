# -*- coding: utf-8 -*-

from odoo import api, models, fields, _
from dateutil.relativedelta import relativedelta
from odoo.tools import float_is_zero

from odoo.tools.safe_eval import safe_eval
import logging
from psycopg2 import OperationalError

_logger = logging.getLogger(__name__)

class InvestmentPeriod(models.Model):
    _name = 'investment.period'
    _inherit = ['mail.thread']
    _description = 'Investment Period'
    _order = 'name desc, id desc'

    name = fields.Char(required=True)

    priority = fields.Selection([
        ('0', 'Low'),
        ('1', 'High'),
    ], default='0', index=True, string="Priority", tracking=True)

    start_date = fields.Date(required=True, tracking=True, default=fields.Date.context_today)
    end_date = fields.Date(required=True, tracking=True, default=fields.Date.context_today)


    domain = fields.Text(default="[('liquid', '=', True)]", required=True, tracking=True)

    company_id = fields.Many2one(
        comodel_name='res.company',
        required=True,
        default=lambda self: self.env.company,
        tracking=True,
        index=True,
    )

    company_currency_id = fields.Many2one(related='company_id.currency_id', string="Company Currency")

    timeseries_ids = fields.Many2many(comodel_name='investment.timeseries', compute='_compute_period', store=True)
    transaction_ids = fields.Many2many(comodel_name='investment.position.transaction', compute='_compute_period', store=True)
    count_timeseries = fields.Integer(compute='_compute_period', store=True)
    count_transactions = fields.Integer(compute='_compute_period', store=True)
    start_position = fields.Monetary(compute='_compute_period', currency_field='company_currency_id', store=True)
    end_position = fields.Monetary(compute='_compute_period', currency_field='company_currency_id', store=True)
    profit = fields.Monetary(compute='_compute_period', currency_field='company_currency_id', store=True, tracking=True)
    annualized_irr = fields.Float(
        string="Annualized IRR",
        compute='_compute_period',
        store=True,
        help=(
            "The money-weighted rate of return (MWRR) is a measure of the performance of an investment. "
            "The MWRR is calculated by finding the rate of return that will set the present values (PV) of all cash flows equal to the value of the initial investment. "
            "The MWRR is equivalent to the internal rate of return (IRR). "
            "MWRR can be compared with the time-weighted return (TWR), which removes the effects of cash in- and outflows. "
        )
    )
    debug_xirr = fields.Text(compute='_compute_period', store=True)


    @api.model
    def get_dashboard(self, domain, specification, offset=0, limit=None, order=None, count_limit=None):
        today = fields.Date.today()
        records = self.search_fetch(domain, list(specification.keys())+['end_date'], offset=offset, limit=limit, order=order)
        records.filtered(lambda r: r.end_date >= today).action_compute()
        values_records = records.web_read(specification)
        return self._format_web_search_read_results(domain, values_records, offset, limit, count_limit)


    def action_view_timeseries(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Investment Timeseries'),
            'res_model': 'investment.timeseries',
            'view_mode': 'list',
            'views': [[False, 'list'], [False, 'form']],
            'domain': [('id', 'in', self.mapped('timeseries_ids').ids)],
        }

    def action_view_transactions(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Investment Transactions'),
            'res_model': 'investment.position.transaction',
            'view_mode': 'list',
            'views': [[False, 'list'], [False, 'form']],
            'domain': [('id', 'in', self.mapped('transaction_ids').ids)],
        }



    def copy(self, default=None):
        default = default or {
            'start_date': self.start_date+relativedelta(years=1),
            'end_date': self.end_date+relativedelta(years=1),
            'name': self.name + ' (copy)',
        }
        return super().copy(default)

    def action_compute(self):
        self._compute_period()

    @api.depends('start_date', 'end_date', 'domain')
    def _compute_period(self):
        from pyxirr import xirr
        today = fields.Date.today()
        records = self
        _logger.info(f"Compute period for: {records}")
        for record in records:
            start_date = record.start_date - relativedelta(days=1)
            end_date = record.end_date if today > record.end_date else today

            record.timeseries_ids = False
            record.transaction_ids = False
            record.start_position = 0.0
            record.end_position = 0.0
            record.profit = 0.0

            domain = safe_eval(record.domain)
            positions = record.env['investment.position'].search(domain)

            values = []
            dates = []
            for position in positions:
                start_series = record.env['investment.timeseries'].search([
                    ('position_id', '=', position.id),
                    ('date', '=', start_date),
                    ('company_id', '=', record.company_id.id),
                ])
                end_series = record.env['investment.timeseries'].search([
                    ('position_id', '=', position.id),
                    ('date', '=', end_date),
                    ('company_id', '=', record.company_id.id),
                ])
                if end_date == today:
                    for serie in end_series:
                        serie.price_id = self.env['investment.asset.price'].search([
                            ('prediction', '=', False),
                            ('asset_id', '=', position.asset_id.id),
                        ], limit=1, order='time desc') # update the latest price when not doing predictions.
                    end_series._compute_timeseries_aggregate()

                record.timeseries_ids += start_series + end_series
                record.start_position += start_series.position
                record.end_position += end_series.position
                record.profit += (end_series.profit - start_series.profit)


                if not float_is_zero(start_series.position, precision_digits=start_series.company_currency_id.decimal_places):
                    values.append(-start_series.position)
                    dates.append(start_date)

                transactions = (end_series.transaction_ids - start_series.transaction_ids).filtered(lambda t: t.usage == 'record')
                record.transaction_ids += transactions

                for trans in transactions:
                    sign = 1
                    if trans.ttype == 'buy':
                        sign = -1
                    elif trans.ttype == 'sell':
                        sign = 1
                    elif trans.ttype == 'yield':
                        sign = 1
                    elif trans.ttype == 'cost':
                        sign = -1

                    if not float_is_zero(trans.payment, precision_digits=trans.company_currency_id.decimal_places):
                        _logger.debug(f"{position.name}, {trans.ttype}: {sign * abs(trans.payment)}")
                        values.append(sign * abs(trans.payment))
                        dates.append(trans.time.date())

                if not float_is_zero(end_series.position, precision_digits=end_series.company_currency_id.decimal_places):
                    values.append(end_series.position)
                    close_on = record.end_date # might be far in the future
                    if end_date == today:
                        close_on = close_on.replace(year=today.year)
                    dates.append(close_on) # calculate as if we would closeed open positions at the end of the year. otherwise 1% gain in first day of the year, would result in 365% gain annualized which adds too much noise.

            annualized_irr = 0
            if values:
                try:
                    annualized_irr = xirr(dates, values)
                except Exception as error:
                    _logger.exception(error)

            record.annualized_irr = annualized_irr
            record.count_timeseries = len(record.timeseries_ids)
            record.count_transactions = len(record.transaction_ids)
            record.debug_xirr = f'{dates=}\n{values=}'
