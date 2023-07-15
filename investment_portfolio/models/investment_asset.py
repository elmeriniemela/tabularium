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

class InvestmentAsset(models.Model):
    _name = 'investment.asset'
    _description = 'Investment Asset'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'parent_category_id, sequence, id'

    sequence = fields.Integer(string='Sequence')

    name = fields.Char(required=True)

    active = fields.Boolean(default=True)

    ticker = fields.Char(required=True)

    notes = fields.Html(sanitize=False, translate=False)

    company_id = fields.Many2one(
        comodel_name='res.company',
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )

    category_id = fields.Many2one(
        comodel_name='investment.category',
        required=True,
        index=True,
    )

    parent_category_id = fields.Many2one(
        related='category_id.parent_id',
        store=True,
    )

    liquid = fields.Boolean(related='category_id.liquid', store=True, readonly=True)

    company_currency_id = fields.Many2one(related='company_id.currency_id', string="Company Currency")

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

    transaction_ids = fields.One2many(
        comodel_name='investment.asset.transaction',
        inverse_name='asset_id',
        domain=[('prediction', '=', False)],
    )

    realized_ids = fields.One2many(
        comodel_name='investment.asset.realized',
        inverse_name='asset_id',
        readonly=True,
    )

    follow = fields.Boolean(compute='_compute_follow', store=True, readonly=False)

    quantity = fields.Float(compute='_compute_aggregate', store=True, digits='Investment Asset quantity', group_operator=None)

    position = fields.Monetary(compute='_compute_aggregate', store=True, currency_field='company_currency_id')
    investment = fields.Monetary(compute='_compute_aggregate', store=True, currency_field='company_currency_id')
    max_investment = fields.Monetary(compute='_compute_aggregate', store=True, currency_field='company_currency_id')

    cost_basis = fields.Monetary(compute='_compute_aggregate', store=True, currency_field='company_currency_id')


    last_update = fields.Datetime(compute='_compute_aggregate', store=True)
    last_price = fields.Monetary(compute='_compute_aggregate', store=True, currency_field='company_currency_id', group_operator=None)
    profit = fields.Monetary(compute='_compute_aggregate', store=True, currency_field='company_currency_id', group_operator='sum')
    profit_percent = fields.Float(compute='_compute_aggregate', store=True, group_operator='avg')
    daily_price = fields.Float(compute='_compute_aggregate', store=True, group_operator='avg', string="1 Day")
    weekly_price = fields.Float(compute='_compute_aggregate', store=True, group_operator='avg', string="1 Week")
    monthly_price = fields.Float(compute='_compute_aggregate', store=True, group_operator='avg', string="1 Month")
    three_month_price = fields.Float(compute='_compute_aggregate', store=True, group_operator='avg', string="3 Months")
    six_month_price = fields.Float(compute='_compute_aggregate', store=True, group_operator='avg', string="6 Months")
    ytd_price = fields.Float(compute='_compute_aggregate', store=True, group_operator='avg', string="YTD")
    one_year_price = fields.Float(compute='_compute_aggregate', store=True, group_operator='avg', string="1 Year")
    three_year_price = fields.Float(compute='_compute_aggregate', store=True, group_operator='avg', string="3 Year")
    five_year_price = fields.Float(compute='_compute_aggregate', store=True, group_operator='avg', string="5 Year")

    thesis = fields.Html(sanitize=False, translate=False)

    integration_id = fields.Many2one(
        comodel_name='investment.integration',
        index=True,
    )

    integration_error_id = fields.Many2one(
        comodel_name='mail.activity',
        copy=False,
        index=True,
    )


    is_cash = fields.Boolean(
        compute='_compute_is_cash',
    )

    plan_transaction_ids = fields.One2many(
        comodel_name='investment.asset.transaction',
        inverse_name='asset_id',
        domain=[('prediction', '=', True)],
    )

    plan_price_ids = fields.One2many(
        comodel_name='investment.asset.price',
        inverse_name='asset_id',
        domain=[('prediction', '=', True)],
    )

    plan_type = fields.Selection(
        selection=[
            ('acquire', 'Acquire'),
            ('exit', 'Exit'),
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


    @api.model
    def cron_create_time_series(self):
        self.env['investment.asset'].search([]).generate_timeserie()

    def generate_timeseries(self):
        today = datetime.date.today()

        precision = self.env['decimal.precision'].precision_get('Investment Asset quantity')
        predict_years = int(self.env['ir.config_parameter'].sudo().get_param('investment_portfolio.predict_years', '25'))

        existing = {(p.asset_id.id, p.date): p for p in self.search([])}

        Timeseries = self.env['investment.timeseries']
        recompute = Timeseries.browse()


        for asset_id in self:
            first = self.env['investment.asset.transaction'].search([('asset_id', '=', asset_id.id)], order='time asc', limit=1)
            if not first:
                _logger.info(f"No transactions on {asset_id.name}")
                continue

            asset_id.generate_plan()
            date = first.time.date()
            _logger.info(f"Make time series for {asset_id.name} starting from {date}")

            while date <= today + relativedelta(years=predict_years):
                prediction = bool(date > today)
                if prediction and float_is_zero(asset_id.quantity, precision_digits=precision):
                    break

                serie = existing.get((asset_id.id, today), None)
                if not serie:
                    serie = Timeseries.create({
                        'asset_id': asset_id.id,
                        'date': date,
                    })
                    existing[(asset_id.id, date)] = serie
                    recompute += serie
                elif asset_id.env.context.get('force_recompute'):
                    recompute += serie
                elif prediction:
                    recompute += serie
                elif date == today:
                    recompute += serie

                if date == today:
                    date = date.replace(month=12, day=31) # start predictions
                elif prediction:
                    date += relativedelta(years=1)
                else:
                    date += datetime.timedelta(days=1)

            yesterday = datetime.date.today() - relativedelta(days=1)
            if first.time.date() <= yesterday:
                recompute += existing[(asset_id.id, yesterday)]

        recompute.exists()._compute_aggregate()

    def generate_plan(self):
        Price = self.env['investment.asset.price']
        Transaction = self.env['investment.asset.transaction']
        predict_years = int(self.env['ir.config_parameter'].sudo().get_param('investment_portfolio.predict_years', '25'))
        today = datetime.date.today()

        # Remove old predictions.

        for asset_id in self:
            if asset_id.plan_auto_realize:
                asset_id.plan_transaction_ids.filtered(lambda t: t.time.date() <= today).prediction = False

            Price.search([('prediction', '=', True), ('asset_id', '=', asset_id.id)]).unlink()
            Transaction.search([('prediction', '=', True), ('asset_id', '=', asset_id.id)]).unlink()
            n = asset_id.plan_months or 0
            date = asset_id.plan_start_date or today
            while date <= today:
                date = banking_date(date+relativedelta(months=1))
                if asset_id.plan_start_date:
                    n -= 1

            end = banking_date(date+relativedelta(months=n))
            r = (asset_id.plan_yearly_interest or 0 + asset_id.plan_yearly_appreciation or 0)/12
            i = 0
            PV = asset_id.position
            P = ((r*PV) / (1-(1+r)**(-n)) if r else 0) - asset_id.plan_fee
            if asset_id.plan_type == 'exit':
                asset_id.plan_payment = P


            curr_price = asset_id.last_price
            price = asset_id.last_price
            while date <= max(today + relativedelta(years=predict_years), end):
                i += 1
                price *= (1+asset_id.plan_yearly_appreciation)**(1/12)
                base_vals = {
                    'prediction': True,
                    'asset_id': asset_id.id,
                    'time': date,
                }

                if date < end:
                    if asset_id.plan_type == 'acquire':
                        if asset_id.plan_payment:
                            trans = {'description': f'{i}: Acquisition', 'quantity': asset_id.plan_payment/price, 'payment': asset_id.plan_payment, 'exchange_rate': price, 'fee': asset_id.plan_fee}
                            Transaction.create({**base_vals, **trans})
                        if asset_id.plan_yield:
                            trans = {'description': f'{i}', 'quantity': 0, 'payment': asset_id.plan_yield, 'exchange_rate': price}
                            Transaction.create({**base_vals, **trans})
                        if asset_id.plan_cost:
                            trans = {'description': f'{i}', 'quantity': 0, 'payment': -asset_id.plan_cost, 'exchange_rate': price}
                            Transaction.create({**base_vals, **trans})

                    elif asset_id.plan_type == 'exit':
                        # Korkopäivät lasketaan todellisten päivien mukaan ja vuodessa on 360 päivää
                        days = (date - banking_date(date-relativedelta(months=1))).days
                        rate = asset_id.plan_yearly_interest*(days/360)
                        interest = PV*rate
                        reduction = P-interest+asset_id.plan_fee
                        dsum = (-reduction) + (-interest) + (asset_id.plan_fee)
                        reduction_vals = {
                            'description': f'{i}: {-reduction:.2f} + {-interest:.2f} + {asset_id.plan_fee:.2f} = {dsum:.2f}',
                            'quantity': float(f'{-reduction/curr_price:.2f}'), 'payment': abs(P), 'fee': asset_id.plan_fee, 'exchange_rate': 1}
                        tr = Transaction.create({**base_vals, **reduction_vals})
                        PV -= reduction
                    else:
                        raise ValueError(f"Invalid plan type {asset_id.plan_type}")

                price_id = Price.search([(key, '=', value) for key, value in base_vals.items()])
                if not price_id:
                    price_id = Price.create({**base_vals, **{'price': price}})
                else:
                    price_id.price = price

                date = banking_date(date+relativedelta(months=1))


            asset_id.plan_total_cash_flow = sum(Transaction.search([('prediction', '=', True), ('asset_id', '=', asset_id.id)]).mapped('cash_flow'))



    @api.model
    def read_group(self, domain, fields, groupby, offset=0, limit=None, orderby=False, lazy=True):
        """
            Override read_group to calculate percentages properly.
        """
        res = super().read_group(domain, fields, groupby, offset=offset, limit=limit, orderby=orderby, lazy=lazy)

        if 'profit_percent' in fields:
            for line in res:
                domain = line.get('__domain') or []
                assets = self.search(line['__domain'])
                total_profits = 0.0
                total_investment = 0.0
                for asset in assets:
                    total_profits += asset.profit
                    total_investment += asset.investment
                line['profit_percent'] = total_profits / total_investment if total_investment else 0.0
        return res


    def _compute_is_cash(self):
        currency_ticker = self.env.company.currency_id.name
        for record in self:
            record.is_cash = record.ticker == currency_ticker

    @api.depends('transaction_ids')
    def _compute_follow(self):
        for record in self:
            record.follow = bool(record.transaction_ids)

    @api.depends(
        'transaction_ids',
        'transaction_ids.quantity',
        'transaction_ids.payment',
        'price_ids',
        'price_ids.price',
        'currency_id',
        'company_currency_id',
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

            closing_price = closing_price_id.currency_id._convert(
                from_amount=closing_price_id.price or 0.0,
                to_currency=record.company_currency_id,
                company=record.env.company,
                date=closing_price_id.time or fields.Datetime.now(),
            )
            return (market_price-closing_price)/closing_price if closing_price else 0.0


        for record in self:
            price_id = record.price_ids[:1]
            record.last_price = price_id.currency_id._convert(
                from_amount=price_id.price or 0.0,
                to_currency=self.company_currency_id,
                company=self.env.company,
                date=price_id.time or fields.Datetime.now(),
            )
            record.update(record._get_position(record.last_price, record.transaction_ids))

            record.last_update = price_id.time
            record.daily_price = percent_change(record, fields.Datetime.now().replace(hour=0, minute=0, second=0), record.last_price)
            record.weekly_price = percent_change(record, fields.Datetime.now().replace(hour=0, minute=0, second=0)-relativedelta(weeks=1), record.last_price)
            record.monthly_price = percent_change(record, fields.Datetime.now().replace(hour=0, minute=0, second=0)-relativedelta(months=1), record.last_price)
            record.three_month_price = percent_change(record, fields.Datetime.now().replace(hour=0, minute=0, second=0)-relativedelta(months=3), record.last_price)
            record.six_month_price = percent_change(record, fields.Datetime.now().replace(hour=0, minute=0, second=0)-relativedelta(months=6), record.last_price)
            record.ytd_price = percent_change(record, fields.Datetime.now().replace(day=1, month=1, hour=0, minute=0, second=0), record.last_price)
            record.one_year_price = percent_change(record, fields.Datetime.now().replace(hour=0, minute=0, second=0)-relativedelta(years=1), record.last_price)
            record.three_year_price = percent_change(record, fields.Datetime.now().replace(hour=0, minute=0, second=0)-relativedelta(years=3), record.last_price)
            record.five_year_price = percent_change(record, fields.Datetime.now().replace(hour=0, minute=0, second=0)-relativedelta(years=5), record.last_price)


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




    def run_integration(self):
        for asset in self:
            _logger.info("Run integration on %s", asset.name)
            integration = asset.integration_id
            if not integration:
                raise ValidationError('Define integration first.')
            integration.execute(asset)
            asset._compute_aggregate() # For some reason, the depends on price_ids does not work...


    def cron_run_integration(self):
        assets = self.search([('integration_id', '!=', False)])
        for asset in assets:
            try:
                with asset.env.cr.savepoint():
                    asset.run_integration()
            except Exception as error:
                _logger.exception(error)
                note = traceback.format_exc().replace('\n', '<br/>')
                if asset.integration_error_id:
                    asset.integration_error_id.note = note
                else:
                    asset.integration_error_id = asset.env['mail.activity'].create({
                        'res_model_id': asset.env['ir.model']._get(asset._name).id,
                        'res_id': asset.id,
                        'activity_type_id': asset.env.ref('mail.mail_activity_data_todo').id,
                        'summary': _('Integration issue'),
                        'date_deadline': datetime.date.today(),
                        'user_id': asset.create_uid.id,
                        'note': note,
                    })
            else:
                asset.integration_error_id.unlink()

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


    def update_realized_fifo(self):
        qty_precision = self.env['decimal.precision'].precision_get('Investment Asset quantity')

        def fill(s, filled):
            quantity = s[filled[0]]['remaining_qty']
            s['sell']['remaining_qty'] -= quantity
            s['buy']['remaining_qty'] -= quantity
            for op in filled:
                assert float_is_zero(s[op]['remaining_qty'], precision_digits=qty_precision), f"Not filled: {s[op]['remaining_qty']}"
                next_tx = next(s[op]['tx_iter'])
                s[op]['tx'] = next_tx
                s[op]['remaining_qty'] = abs(next_tx.quantity)

        for asset in self:
            valid = self.env['investment.asset.realized'].browse()

            existing = {(r.sell_batch_id, r.buy_batch_id): r for r in asset.realized_ids}
            transactions = asset.transaction_ids.sorted(key=lambda s: s.time)
            sells = transactions.filtered(lambda t: t.ttype == 'sell')
            buys = transactions.filtered(lambda t: t.ttype == 'buy')
            if buys and sells:
                state = {
                    'buy': {'tx_iter': iter(buys), 'tx': False, 'remaining_qty': 0},
                    'sell': {'tx_iter': iter(sells), 'tx': False, 'remaining_qty': 0},
                }
                fill(state, ['buy', 'sell']) # Initial assignment of the 'tx' and 'remaining_qty' keys.
                while True:
                    key = (state['sell']['tx'], state['buy']['tx'])
                    vals = {
                        'asset_id': asset.id,
                        'sell_batch_id': state['sell']['tx'].id,
                        'buy_batch_id': state['buy']['tx'].id,
                    }
                    compare = float_compare(state['buy']['remaining_qty'], state['sell']['remaining_qty'], precision_digits=qty_precision)
                    if compare == 0: # Equal
                        filled = ['buy', 'sell']
                    elif compare == -1: # Buy quantity was smaller
                        filled = ['buy']
                    elif compare: # Sell quantity was smaller
                        filled = ['sell']
                    else:
                        raise ValueError(f"Invalid float_compare {compare}")

                    vals['quantity'] = state[filled[0]]['remaining_qty']
                    if key in existing:
                        existing[key].write(vals)
                    else:
                        existing[key] = asset.realized_ids.create(vals)

                    existing[key]._compute_profit()
                    valid |= existing[key]

                    try:
                        fill(state, filled)
                    except StopIteration:
                        break # no more buy or sell transactions left.

            (asset.realized_ids - valid).unlink()


