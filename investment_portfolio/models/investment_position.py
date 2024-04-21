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


def banking_date(date):
    return rrule.rrule(rrule.DAILY, byweekday=(rrule.MO,rrule.TU,rrule.WE,rrule.TH,rrule.FR), dtstart=date.replace(day=15))[0].date()



class InvestmentPosition(models.Model):
    _name = 'investment.position'
    _description = 'Investment Position'
    _order = 'portfolio_id, sequence, id'
    _inherits = {'investment.asset': 'asset_id'}
    _inherit = ['mail.thread', 'mail.activity.mixin']

    active = fields.Boolean(default=True)

    asset_id = fields.Many2one(
        comodel_name='investment.asset', string='Ticker',
        auto_join=True, index=True, ondelete='cascade', required=True)

    name = fields.Char(required=True)

    sequence = fields.Integer(string='Sequence')

    portfolio_id = fields.Many2one(
        comodel_name='investment.portfolio',
        required=True,
        index=True,
    )

    notes = fields.Html(sanitize=False, translate=False)

    company_id = fields.Many2one(
        comodel_name='res.company',
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )

    company_currency_id = fields.Many2one(related='company_id.currency_id', string="Company Currency")


    is_company_currency = fields.Boolean(
        compute='_compute_is_company_currency'
    )

    endpoint_id = fields.Many2one(related='asset_id.endpoint_id')

    transaction_ids = fields.One2many(
        comodel_name='investment.position.transaction',
        inverse_name='position_id',
        domain=[('usage', '=', 'record')],
    )

    realized_ids = fields.One2many(
        comodel_name='investment.asset.realized',
        inverse_name='position_id',
        readonly=True,
    )

    thesis = fields.Html(sanitize=False, translate=False)

    follow = fields.Boolean(compute='_compute_follow', store=True, readonly=False)

    quantity = fields.Float(compute='_compute_position_aggregate', store=True, digits='Investment Asset quantity', group_operator=None)
    position = fields.Monetary(compute='_compute_position_aggregate', store=True, currency_field='company_currency_id', help="Current value of this position.")
    investment = fields.Monetary(compute='_compute_position_aggregate', store=True, currency_field='company_currency_id')
    max_investment = fields.Monetary(compute='_compute_position_aggregate', store=True, currency_field='company_currency_id')
    cost_basis = fields.Monetary(compute='_compute_position_aggregate', store=True, currency_field='company_currency_id', help="Average price across every purchase.")
    last_price_own_currency = fields.Monetary(string="Last Price (own currency)", compute='_compute_position_aggregate', store=True, currency_field='company_currency_id', group_operator=None)

    profit = fields.Monetary(compute='_compute_position_aggregate', store=True, currency_field='company_currency_id', group_operator='sum')
    profit_percent = fields.Float(compute='_compute_position_aggregate', store=True, group_operator='avg')


    is_cash = fields.Boolean(
        compute='_compute_is_cash',
    )

    plan_transaction_ids = fields.One2many(
        comodel_name='investment.position.transaction',
        inverse_name='position_id',
        domain=[('usage', '=', 'prediction')],
    )

    plan_type = fields.Selection(
        selection=[
            ('acquire', 'Acquire'),
            ('exit', 'Exit'),
            ('cashflow', 'Yield/Cost'),
        ],
        default='acquire',
        required=True,
    )
    plan_start_date = fields.Date()
    plan_months = fields.Integer(default=300)
    plan_payment = fields.Monetary(string="Plan Cash Flow")
    plan_yield = fields.Monetary(default=0.0)
    plan_cost = fields.Monetary(default=0.0)
    plan_fee = fields.Monetary(default=0.0)
    plan_yearly_appreciation = fields.Float(group_operator='avg', default=0.0, digits='Investment Asset Interest')
    plan_yearly_interest = fields.Float(group_operator='avg', default=0.0, digits='Investment Asset Interest')
    plan_total_cash_flow = fields.Monetary(readonly=True)
    plan_auto_realize = fields.Boolean()
    plan_allow_past = fields.Boolean()

    @api.depends(
        'transaction_ids',
        'transaction_ids.quantity',
        'transaction_ids.payment',
        'last_price_id',
        'currency_id',
        'company_currency_id',
    )
    def _compute_position_aggregate(self):
        for record in self:
            record.last_price_own_currency = record.last_price_id.currency_id._convert(
                from_amount=record.last_price_id.price or 0.0,
                to_currency=record.company_currency_id,
                company=record.company_id,
                date=record.last_price_id.time or fields.Datetime.now(),
            )
            record.update(record._get_position(record.last_price_own_currency, record.transaction_ids))



    def run_integration(self):
        self.mapped('asset_id').run_integration()

    @api.model
    def cron_create_time_series(self):
        self.env['investment.position'].search([]).generate_timeseries()

    def generate_timeseries(self):
        # Re-generate plans first, as this removes price ids and cascades existing timeseries.

        for position_id in self:
            predicted = self.env['investment.asset.price'].search([
                ('asset_id', '=', position_id.asset_id.id),
                ('prediction', '=', True),
            ])
            predicted.unlink()
            position_id.generate_plan()

        today = datetime.date.today()

        precision = self.env['decimal.precision'].precision_get('Investment Asset quantity')
        predict_years = int(self.env['ir.config_parameter'].sudo().get_param('investment_portfolio.predict_years', '25'))

        Timeseries = self.env['investment.timeseries']

        existing = {(t.position_id.id, t.date): t for t in Timeseries.search([])}
        recompute = Timeseries.browse()

        for position_id in self:
            first_tx = self.env['investment.position.transaction'].search([('position_id', '=', position_id.id)], order='time asc', limit=1)
            first_pr = self.env['investment.asset.price'].search([('asset_id', '=', position_id.asset_id.id)], order='time asc', limit=1)
            if not first_tx:
                _logger.info(f"No transactions on {position_id.name}")
                continue

            if not first_pr:
                _logger.warning(f"No prices for {position_id.name}")
                continue

            if first_tx.time < first_pr.time:
                _logger.warning(f"Position {position_id.name} has a transaction before any price information.")
                date = start_date = first_pr.time.date()
            else:
                date = start_date = first_tx.time.date()


            _logger.info(f"Make time series for {position_id.name} starting from {date}")

            while date <= today + relativedelta(years=predict_years):
                prediction = bool(date > today)
                if prediction and float_is_zero(position_id.quantity, precision_digits=precision):
                    break

                serie = existing.get((position_id.id, date), None)
                if not serie:
                    if (not prediction) and (date >= position_id.asset_id.last_update.date()):
                        price_id = self.env['investment.asset.price'].search([
                            ('prediction', '=', False),
                            ('asset_id', '=', position_id.asset_id.id),
                        ], limit=1, order='time desc') # just use latest instead of making predictions for assets without recent price updates.
                    else:
                        price_id = position_id.asset_id.price_at_date(date)

                    serie = Timeseries.create({
                        'position_id': position_id.id,
                        'date': date,
                        'price_id': price_id.id,
                    })
                    existing[(position_id.id, date)] = serie
                    recompute += serie
                elif prediction:
                    recompute += serie
                elif position_id.env.context.get('force_recompute') or (date == today):
                    serie.price_id = self.env['investment.asset.price'].search([
                        ('prediction', '=', False),
                        ('asset_id', '=', position_id.asset_id.id),
                    ], limit=1, order='time desc') # update the latest price when not doing predictions.
                    recompute += serie

                if date == today:
                    date = date.replace(month=12, day=31) # start predictions
                elif prediction:
                    date += relativedelta(years=1)
                else:
                    date += datetime.timedelta(days=1)


            yesterday = datetime.date.today() - relativedelta(days=1)
            yestkey = (position_id.id, yesterday)
            if start_date <= yesterday and yestkey in existing:
                recompute += existing[yestkey]

            todaykey = (position_id.id, today)
            if not todaykey in existing:
                serie = Timeseries.create({
                    'position_id': position_id.id,
                    'date': today,
                })
                existing[todaykey] = serie
                recompute += serie

        recompute.exists()._compute_timeseries_aggregate()

    def generate_plan(self):
        Transaction = self.env['investment.position.transaction']
        predict_years = int(self.env['ir.config_parameter'].sudo().get_param('investment_portfolio.predict_years', '25'))
        today = datetime.date.today()

        # Remove old predictions.

        for position_id in self:
            if not position_id.quantity and position_id.plan_type != 'cashflow':
                _logger.info("Skip plan for %s as we have no position on it.", position_id.name)
                continue

            _logger.info("Generate plan for %s.", position_id.name)
            if position_id.plan_auto_realize:
                position_id.plan_transaction_ids.filtered(lambda t: t.time.date() <= today).prediction = False

            Transaction.search([('prediction', '=', True), ('position_id', '=', position_id.id)]).unlink()
            n = position_id.plan_months or 0
            date = banking_date(position_id.plan_start_date or today)
            if position_id.plan_auto_realize or not position_id.plan_allow_past:
                while date <= today:
                    date = banking_date(date+relativedelta(months=1))
                    if position_id.plan_start_date:
                        n -= 1
            if n <= 0:
                continue

            end = banking_date(date+relativedelta(months=n))
            r = (position_id.plan_yearly_interest or 0 + position_id.expected_yearly_appreciation or 0)/12
            i = 0
            PV = position_id.position
            P = ((r*PV) / (1-(1+r)**(-n)) if r else 0) - position_id.plan_fee
            if position_id.plan_type == 'exit':
                position_id.plan_payment = P


            curr_price = position_id.last_price
            price = position_id.last_price
            while date <= max(today + relativedelta(years=predict_years), end):
                i += 1
                price *= (1+position_id.expected_yearly_appreciation)**(1/12)
                base_vals = {
                    'prediction': True,
                    'position_id': position_id.id,
                    'time': date,
                }

                if date < end:
                    if position_id.plan_type == 'acquire':
                        if position_id.plan_payment:
                            trans = {'description': f'{i}: Acquisition', 'quantity': position_id.plan_payment/price, 'payment': position_id.plan_payment, 'exchange_rate': price, 'fee': position_id.plan_fee}
                            Transaction.create({**base_vals, **trans})
                        if position_id.plan_yield:
                            trans = {'description': f'{i}', 'quantity': 0, 'payment': position_id.plan_yield, 'exchange_rate': price}
                            Transaction.create({**base_vals, **trans})
                        if position_id.plan_cost:
                            trans = {'description': f'{i}', 'quantity': 0, 'payment': -position_id.plan_cost, 'exchange_rate': price}
                            Transaction.create({**base_vals, **trans})

                    elif position_id.plan_type == 'exit':
                        # Korkopäivät lasketaan todellisten päivien mukaan ja vuodessa on 360 päivää
                        days = (date - banking_date(date-relativedelta(months=1))).days
                        rate = position_id.plan_yearly_interest*(days/360)
                        interest = PV*rate
                        reduction = P-interest+position_id.plan_fee
                        dsum = (-reduction) + (-interest) + (position_id.plan_fee)
                        reduction_vals = {
                            'description': f'{i}: {-reduction:.2f} + {-interest:.2f} + {position_id.plan_fee:.2f} = {dsum:.2f}',
                            'quantity': float(f'{-reduction/curr_price:.2f}'), 'payment': abs(P), 'fee': position_id.plan_fee, 'exchange_rate': 1}
                        tr = Transaction.create({**base_vals, **reduction_vals})
                        tr.fee = position_id.plan_fee
                        PV -= reduction
                    elif position_id.plan_type == 'cashflow':
                        if position_id.plan_yield:
                            trans = {'description': f'{i}', 'quantity': 0, 'payment': position_id.plan_yield, 'exchange_rate': price}
                            tr = Transaction.create({**base_vals, **trans})
                        if position_id.plan_cost:
                            trans = {'description': f'{i}', 'quantity': 0, 'payment': -position_id.plan_cost, 'exchange_rate': price}
                            tr = Transaction.create({**base_vals, **trans})
                    else:
                        raise ValueError(f"Invalid plan type {position_id.plan_type}")

                date = banking_date(date+relativedelta(months=1))


            position_id.plan_total_cash_flow = sum(Transaction.search([('prediction', '=', True), ('position_id', '=', position_id.id)]).mapped('cash_flow'))

    @api.model
    def read_group(self, domain, fields, groupby, offset=0, limit=None, orderby=False, lazy=True):
        """
            Override read_group to calculate percentages properly.
        """
        res = super().read_group(domain, fields, groupby, offset=offset, limit=limit, orderby=orderby, lazy=lazy)

        if 'profit_percent' in fields:
            for line in res:
                domain = line.get('__domain') or []
                positions = self.search(line['__domain'])
                total_profits = 0.0
                total_investment = 0.0
                for position in positions:
                    total_profits += position.profit
                    total_investment += position.investment
                line['profit_percent'] = total_profits / total_investment if total_investment else 0.0
        return res

    @api.depends('currency_id', 'company_id')
    def _compute_is_company_currency(self):
        for rec in self:
            rec.is_company_currency = rec.currency_id == rec.company_currency_id


    def _compute_is_cash(self):
        currency_ticker = self.env.company.currency_id.name
        for record in self:
            record.is_cash = record.ticker == currency_ticker

    @api.depends('transaction_ids')
    def _compute_follow(self):
        for record in self:
            record.follow = bool(record.transaction_ids)


    def update_realized_fifo(self):
        class TxJoin:
            def __init__(self, buys, sells, precision):
                self.buys, self.sells, self.precision = buys, sells, precision

            def __iter__(self):
                self._iter_state = {
                    'buy': {'iter': iter(self.buys), 'tx': False, 'qty': 0},
                    'sell': {'iter': iter(self.sells), 'tx': False, 'qty': 0},
                }
                return self

            def __next__(self):
                s = self._iter_state
                sub = min(s['buy']['qty'], s['sell']['qty'])
                for op in ['sell', 'buy']:
                    s[op]['qty'] -= sub
                    if float_is_zero(s[op]['qty'], precision_digits=self.precision):
                        tx = next(s[op]['iter']) # This will eventually raise StopIteration
                        s[op]['tx'] = tx
                        s[op]['qty'] = abs(tx.quantity)
                return s['sell']['tx'], s['buy']['tx'], min(s['buy']['qty'], s['sell']['qty'])

        qty_precision = self.env['decimal.precision'].precision_get('Investment Asset quantity')
        for position in self:
            valid = self.env['investment.asset.realized'].browse()

            existing = {(r.sell_batch_id, r.buy_batch_id): r for r in position.realized_ids}
            transactions = position.transaction_ids.sorted(key=lambda s: s.time)
            sells = transactions.filtered(lambda t: t.ttype == 'sell')
            sell_vals = {
                'description': 'Simulated Realization',
                'quantity': position.quantity,
                'payment': position.quantity * position.last_price_own_currency,
                'exchange_rate': position.last_price,
                'usage': 'realized',
                'position_id': position.id,
                'time': fields.Datetime.now(),
            }
            simulated = sells.search([('position_id', '=', position.id), ('usage', '=', 'realized')])
            assert len(simulated) <= 1

            if position.quantity:
                if simulated:
                    simulated.write(sell_vals)
                else:
                    simulated = simulated.create(sell_vals)
                sells += simulated
            else:
                simulated.unlink()

            buys = transactions.filtered(lambda t: t.ttype == 'buy')
            if buys and sells:
                for (sell, buy, quantity) in TxJoin(buys, sells, qty_precision):
                    key = (sell, buy)
                    vals = {
                        'position_id': position.id,
                        'sell_batch_id': sell.id,
                        'buy_batch_id': buy.id,
                        'quantity': quantity,
                    }
                    if key in existing:
                        existing[key].write(vals)
                    else:
                        existing[key] = position.realized_ids.create(vals)

                    existing[key]._compute_profit()
                    valid |= existing[key]

            (position.realized_ids - valid).unlink()


    def _get_position(self, market_price, transaction_ids):
        self.ensure_one()

        quantity = 0.0
        investment = 0.0
        max_investment = 0.0
        for tx in transaction_ids[::-1]:
            quantity += tx.quantity
            investment += tx.cash_flow
            max_investment = max(investment, max_investment)

        position = quantity * market_price
        profit = position-investment

        return {
            'position': position,
            'quantity': quantity,
            'profit': profit,
            'investment': investment,
            'cost_basis': investment/quantity if quantity else 0,
            'profit_percent': profit/max_investment if max_investment else 0,
            'max_investment': max_investment,
        }