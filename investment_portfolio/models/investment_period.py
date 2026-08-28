# -*- coding: utf-8 -*-

from odoo import api, models, fields, _
from dateutil.relativedelta import relativedelta
from odoo.tools import float_is_zero

from odoo.tools.safe_eval import safe_eval
import logging
import math

from collections import defaultdict

_logger = logging.getLogger(__name__)


def _xnpv_scaled(log_rate, periods, values):
    """Return XNPV and its derivative with a shared overflow-safe scale."""
    terms = [
        (math.log(abs(value)) - log_rate * period, math.copysign(1.0, value), period)
        for period, value in zip(periods, values)
        if value
    ]
    scale = max(log_value for log_value, _sign, _period in terms)
    result = 0.0
    derivative = 0.0
    for log_value, sign, period in terms:
        scaled_value = sign * math.exp(log_value - scale)
        result += scaled_value
        derivative -= period * scaled_value
    return result, derivative


def xirr(dates, values, guess=0.1):
    """Calculate an annualized IRR for irregular cash flows without NumPy."""
    if len(dates) != len(values) or len(values) < 2:
        raise ValueError("XIRR requires matching dates and values")
    values = [float(value) for value in values]
    if not any(value > 0 for value in values) or not any(value < 0 for value in values):
        raise ValueError("XIRR requires at least one positive and one negative cash flow")

    start = min(dates)
    periods = [(cashflow_date - start).days / 365.0 for cashflow_date in dates]
    if not any(periods):
        raise ValueError("XIRR cash flows must occur on different dates")

    initial = math.log1p(guess) if guess > -1 else math.log1p(0.1)
    log_rate = initial
    for _iteration in range(100):
        value, derivative = _xnpv_scaled(log_rate, periods, values)
        if abs(value) < 1e-12:
            return math.expm1(log_rate)
        if not derivative:
            break
        next_log_rate = log_rate - value / derivative
        if not math.isfinite(next_log_rate) or not -50 < next_log_rate < 50:
            break
        if abs(next_log_rate - log_rate) < 1e-12:
            return math.expm1(next_log_rate)
        log_rate = next_log_rate

    # Newton's method can jump past a root for unusual cash-flow patterns. Find
    # every sign-changing interval and use the one nearest the conventional 10%
    # starting guess.
    brackets = []
    left = -50.0
    left_value, _derivative = _xnpv_scaled(left, periods, values)
    for index in range(1, 401):
        right = -50.0 + index * 0.25
        right_value, _derivative = _xnpv_scaled(right, periods, values)
        if not right_value:
            return math.expm1(right)
        if math.copysign(1.0, left_value) != math.copysign(1.0, right_value):
            brackets.append((left, right, left_value, right_value))
        left, left_value = right, right_value
    if not brackets:
        raise ValueError("XIRR did not converge")

    left, right, left_value, _right_value = min(
        brackets,
        key=lambda bracket: abs((bracket[0] + bracket[1]) / 2 - initial),
    )
    for _iteration in range(200):
        middle = (left + right) / 2
        middle_value, _derivative = _xnpv_scaled(middle, periods, values)
        if abs(middle_value) < 1e-12 or right - left < 1e-12:
            return math.expm1(middle)
        if math.copysign(1.0, left_value) == math.copysign(1.0, middle_value):
            left, left_value = middle, middle_value
        else:
            right = middle
    raise ValueError("XIRR did not converge")


class InvestmentPeriod(models.Model):
    _name = 'investment.period.position'
    _description = 'Investment Period Position'
    _rec_name = 'position_id'
    _order = 'profit, id'

    company_id = fields.Many2one(related='period_id.company_id')
    company_currency_id = fields.Many2one(related='company_id.currency_id', string="Company Currency")

    position_id = fields.Many2one(
        comodel_name='investment.position',
        required=True,
        readonly=True,
        ondelete='cascade',
    )

    period_id = fields.Many2one(
        comodel_name='investment.period',
        required=True,
        readonly=True,
        ondelete='cascade',
    )

    profit = fields.Monetary(currency_field='company_currency_id')



class InvestmentPeriod(models.Model):
    _name = 'investment.period'
    _inherit = ['mail.thread', 'aquire.lock.mixin']
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
    position_ids = fields.One2many(comodel_name='investment.period.position', inverse_name='period_id', compute='_compute_period', store=True)
    count_timeseries = fields.Integer(compute='_compute_period', store=True)
    count_transactions = fields.Integer(compute='_compute_period', store=True)
    count_positions = fields.Integer(compute='_compute_period', store=True)
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
        records = self.mapped('timeseries_ids')
        return {
            'type': 'ir.actions.act_window',
            'name': _('Investment Timeseries'),
            'res_model': records._name,
            'view_mode': 'list',
            'views': [[False, 'list'], [False, 'form']],
            'domain': [('id', 'in', records.ids)],
        }

    def action_view_transactions(self):
        records = self.mapped('transaction_ids')
        return {
            'type': 'ir.actions.act_window',
            'name': _('Investment Transactions'),
            'res_model': records._name,
            'view_mode': 'list',
            'views': [[False, 'list'], [False, 'form']],
            'domain': [('id', 'in', records.ids)],
        }

    def action_view_positions(self):
        records = self.mapped('position_ids')
        return {
            'type': 'ir.actions.act_window',
            'name': _('Investment Positions'),
            'res_model': records._name,
            'view_mode': 'list',
            'views': [[False, 'list'], [False, 'form']],
            'domain': [('id', 'in', records.ids)],
        }



    def copy(self, default=None):
        default = default or {
            'start_date': self.start_date+relativedelta(years=1),
            'end_date': self.end_date+relativedelta(years=1),
            'name': self.name + ' (copy)',
        }
        return super().copy(default)

    def action_compute(self):
        if not self.acquire_lock():
            _logger.info("Unable to compute as records are locked %s", self)
            return

        self._compute_period()

    @api.depends('start_date', 'end_date', 'domain')
    def _compute_period(self):
        today = fields.Date.today()
        records = self
        _logger.info(f"Compute period for: {records}")
        Serie = self.env['investment.timeseries'].browse().sudo()
        pending = []
        future_ends = Serie
        for record in records.sudo():
            start_date = record.start_date - relativedelta(days=1)
            is_future = record.end_date >= today
            end_date = today if is_future else record.end_date

            record.timeseries_ids = False
            record.transaction_ids = False
            record.start_position = 0.0
            record.end_position = 0.0
            record.profit = 0.0

            domain = safe_eval(record.domain)
            posdomain = record.env['investment.position'].search(domain)


            fnames = ['position', 'profit', 'company_currency_id', 'transaction_ids',]
            all_starts = Serie.search_fetch(
                domain=[
                    ('position_id', 'in', posdomain.ids),
                    ('date', '=', start_date),
                    ('company_id', '=', record.company_id.id),
                ],
                field_names=fnames,
            )

            all_ends = Serie.search_fetch(
                domain=[
                    ('position_id', 'in', posdomain.ids),
                    ('date', '=', end_date),
                    ('company_id', '=', record.company_id.id),
                ],
                field_names=fnames,
            )

            if is_future:
                future_ends += all_ends

            pending.append((record, start_date, is_future, posdomain, all_starts, all_ends))

        if future_ends: # call these heavy functions for all required records at once outside of the main loop.
            future_ends._compute_timeseries_aggregate()

        for record, start_date, is_future, posdomain, all_starts, all_ends in pending:
            decimal_places = record.company_id.currency_id.decimal_places
            starts_map = {s.position_id: s for s in all_starts} # date_timeseries_unique
            ends_map = {s.position_id: s for s in all_ends} # date_timeseries_unique


            values = []
            dates = []

            positions = defaultdict(float)


            txs = record.env['investment.position.transaction'].browse().sudo()
            srs = Serie.browse()
            for pos in posdomain:
                start_series = starts_map.get(pos, Serie.browse())
                end_series = ends_map.get(pos, Serie.browse())
                srs += start_series + end_series
                record.start_position += start_series.position
                record.end_position += end_series.position
                record.profit += (end_series.profit - start_series.profit)


                if not float_is_zero(start_series.position, precision_digits=decimal_places):
                    positions[start_series.position_id] += -start_series.position
                    values.append(-start_series.position)
                    dates.append(start_date)

                transactions = (end_series.transaction_ids - start_series.transaction_ids).filtered(lambda t: t.usage == 'record')
                txs += transactions

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

                    if not float_is_zero(trans.payment, precision_digits=decimal_places):
                        # _logger.info(f"{pos.name}, {trans.ttype}: {sign * abs(trans.payment)}") # do not trigger unecdessary reads
                        positions[trans.position_id] += sign * abs(trans.payment)
                        values.append(sign * abs(trans.payment))
                        dates.append(trans.time.date())

                if not float_is_zero(end_series.position, precision_digits=decimal_places):
                    values.append(end_series.position)
                    positions[end_series.position_id] += end_series.position
                    close_on = record.end_date # might be far in the future
                    if is_future:
                        close_on = close_on.replace(year=today.year)
                    dates.append(close_on) # calculate as if we would closeed open positions at the end of the year. otherwise 1% gain in first day of the year, would result in 365% gain annualized which adds too much noise.

            annualized_irr = 0
            if values:
                try:
                    annualized_irr = xirr(dates, values)
                except Exception as error:
                    _logger.exception(error)

            record.annualized_irr = annualized_irr
            record.timeseries_ids = srs
            record.transaction_ids = txs
            record.count_timeseries = len(record.timeseries_ids)
            record.count_transactions = len(record.transaction_ids)
            record.debug_xirr = f'{dates=}\n{values=}'

            existing_pos = {r.position_id: r for r  in record.position_ids}
            seen = record.env['investment.period.position'].browse()
            for position, profit in positions.items():
                if position in existing_pos:
                    existing_pos[position].profit = profit
                else:
                    existing_pos[position] = record.env['investment.period.position'].create({
                        'position_id': position.id,
                        'period_id': record._origin.id,
                        'profit': profit,
                    })

                seen += existing_pos[position]

            record.position_ids = seen
            record.count_positions = len(seen)
