# -*- coding: utf-8 -*-

from odoo import api, models, fields, _
from odoo.exceptions import ValidationError
from odoo.tools import float_is_zero, float_compare, date_utils
from odoo.osv import expression
import traceback, logging
from dateutil.relativedelta import relativedelta
import random
import pytz

from odoo.tools.safe_eval import safe_eval, test_python_expr, wrap_module, datetime, dateutil

import lxml
lxml_mods = ['etree']
for mod in lxml_mods:
    __import__('lxml.%s' % mod)
lxml = wrap_module(__import__('lxml'), {mod: getattr(lxml, mod).__all__ for mod in lxml_mods})

requests = wrap_module(__import__('requests'), ['get', 'post'])
io = wrap_module(__import__('io'), ['StringIO', 'BytesIO'])
pandas = wrap_module(__import__('pandas'), ['read_csv', 'read_excel'])


_logger = logging.getLogger(__name__)

class Currency(models.Model):
    _inherit = 'res.currency'

    def cron_update_rate(self, modes=['realtime', 'intraday', 'daily']):
        Rate = self.env['res.currency.rate']
        Asset = self.env['investment.asset']
        currencies = {c.name: c for c in self.search([])}
        from_currency = self.env.company.currency_id.name
        api_key = self.env['ir.config_parameter'].sudo().get_param('alpha.vantage.api.key')
        for to_currency, currency_id in currencies.items():
            rates = {}
            for mode in modes:
                try:
                    if mode == 'realtime':
                        resp = requests.get(f'https://www.alphavantage.co/query?function=CURRENCY_EXCHANGE_RATE&from_currency={from_currency}&to_currency={to_currency}&apikey={api_key}')
                        json_data = resp.json()
                        key = "Realtime Currency Exchange Rate"
                        if key not in json_data:
                            # Requires premium
                            raise ValidationError(str(json_data))
                        vals = json_data[key]
                        rates = {dateutil.parser.parse(vals['6. Last Refreshed']).date(): float(vals['5. Exchange Rate'])}
                    elif mode == 'intraday':
                        resp = requests.get(f'https://www.alphavantage.co/query?function=FX_INTRADAY&from_symbol={from_currency}&to_symbol={to_currency}&interval=5min&apikey={api_key}')
                        vals = resp.json()["Time Series FX (5min)"]
                        rates = {}
                        for d_str, w in vals.items():
                            date = dateutil.parser.parse(d_str).date()
                            if date not in rates:
                                rates[date] = float(w['4. close'])
                    elif mode == 'daily':
                        resp = requests.get(f'https://www.alphavantage.co/query?function=FX_DAILY&from_symbol={from_currency}&to_symbol={to_currency}&apikey={api_key}')
                        vals = resp.json()["Time Series FX (Daily)"]
                        rates = {dateutil.parser.parse(d_str).date(): float(w['4. close']) for d_str, w in vals.items() }
                    elif mode == 'weekly':
                        resp = requests.get(f'https://www.alphavantage.co/query?function=FX_WEEKLY&from_symbol={from_currency}&to_symbol={to_currency}&apikey={api_key}')
                        vals = resp.json()["Time Series FX (Weekly)"]
                        rates = {dateutil.parser.parse(d_str).date(): float(w['4. close']) for d_str, w in vals.items() }
                    else:
                        raise ValidationError(f"Invalid {mode=}")
                except Exception as error:
                    _logger.exception(error)
                else:
                    break

            if rates:
                _logger.info(f"Update {mode} rates on {to_currency}")
                for date, rate in rates.items():
                    rate_record = Rate.search([
                        ('currency_id', '=', currency_id.id),
                        ('name', '=', date),
                    ])
                    if rate_record:
                        rate_record.rate = rate
                    else:
                        Rate.create({
                            'name': date,
                            'currency_id': currency_id.id,
                            'rate': rate,
                        })

            Asset.search([('currency_id', '=', currency_id.id)])._compute_aggregate()


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

    prediction = fields.Boolean(related='price_id.prediction')

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
            prediction = [('prediction', '=', record.date > fields.Date.today())]
            time_cutoff = datetime.datetime(t.year, t.month, t.day, 20, 0, 0)
            domain = [
                ('time', '<=', time_cutoff),
                ('asset_id', '=', record.asset_id.id),
            ]
            record.transaction_ids = record.env['investment.asset.transaction'].search(domain) # latest but before date
            price_id = record.env['investment.asset.price'].search(domain+prediction, limit=1, order='time desc') # latest but before time_cutoff
            if not price_id:
                _logger.warning("No price: %s", domain+prediction)
                price_id = record.env['investment.asset.price'].search(domain, limit=1, order='time desc') # latest but before time_cutoff
            record.price_id = price_id
            if not price_id:
                _logger.warning("No price: %s", domain)
                market_price = 0.0
            elif price_id.time.date() == t:
                market_price = price_id.price
            else:
                next_price_id = record.env['investment.asset.price'].search([
                    ('time', '>=', time_cutoff),
                    ('asset_id', '=', record.asset_id.id),
                ]+prediction, limit=1, order='time asc') # earliest but after time_cutoff
                if next_price_id:
                    # Linear Interpolation
                    slope = (next_price_id.price - price_id.price) / (next_price_id.time - price_id.time).days
                    market_price = price_id.price + slope*(time_cutoff-price_id.time).days
                else:
                    market_price = price_id.price


            record.last_price = price_id.currency_id._convert(
                from_amount=market_price,
                to_currency=self.company_currency_id,
                company=self.env.company,
                date=price_id.time or fields.Datetime.now(),
            )

            vals = record.asset_id._get_position(record.last_price, record.transaction_ids).items()
            vals = {k: v for k, v in vals if k in record._fields}
            assert vals, "Filtering with record._fields failed."
            record.update(vals)




    @api.model
    def cron_create_time_series(self):

        today = datetime.date.today()

        precision = self.env['decimal.precision'].precision_get('Investment Asset quantity')
        predict_years = int(self.env['ir.config_parameter'].sudo().get_param('investment_portfolio.predict_years', '25'))

        existing = {(p.asset_id.id, p.date): p for p in self.search([])}

        recompute = self.browse()


        for asset_id in self.env['investment.asset'].search([]):
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

                if (asset_id.id, date) not in existing:
                    existing[(asset_id.id, date)] = self.create({
                        'asset_id': asset_id.id,
                        'date': date,
                    })
                    recompute += existing[(asset_id.id, date)]

                if prediction:
                    recompute += existing[(asset_id.id, date)]

                if date == today:
                    serie_today = existing[(asset_id.id, today)]
                    serie_today._compute_aggregate()

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


class InvestmentMilestone(models.Model):
    _name = 'investment.milestone'
    _inherit = ['mail.thread']
    _description = 'Investment Milestone'
    _order = 'date asc'

    name = fields.Char(required=True)

    date = fields.Date(required=True, tracking=True)

    domain = fields.Text(default="[('liquid', '=', True)]", required=True, tracking=True)

    position = fields.Monetary(string="Target Position", required=True, currency_field='company_currency_id', tracking=True)

    inflation_rate = fields.Float(default=0.07, tracking=True)

    real_position = fields.Monetary(compute='_compute_real_position', currency_field='company_currency_id')

    company_id = fields.Many2one(
        comodel_name='res.company',
        required=True,
        default=lambda self: self.env.company,
        tracking=True,
        index=True,
    )

    company_currency_id = fields.Many2one(related='company_id.currency_id', string="Company Currency")

    state = fields.Selection(
        selection=[
            ('ahead', 'Ahead'),
            ('behind', 'Behind'),
            ('missed', 'Missed'),
            ('reached', 'Reached'),
        ],
        compute='_compute_state',
    )

    predicted_position = fields.Monetary(
        string="Predicted/Actual Position",
        compute='_compute_state',
        currency_field='company_currency_id',
    )

    difference = fields.Monetary(
        compute='_compute_state',
        currency_field='company_currency_id',
    )

    timeseries_ids = fields.Many2many(
        comodel_name='investment.timeseries',
        compute='_compute_state',
    )

    def copy(self, default=None):
        default = default or {
            'date': self.date+relativedelta(years=1),
            'name': self.name + ' (copy)',
        }
        return super().copy(default)

    def copy_button(self):
        self.ensure_one()
        self.copy()

    @api.depends('position', 'date')
    def _compute_state(self):
        today = fields.Date.today()
        for record in self:
            domain = safe_eval(record.domain)
            record.timeseries_ids = record.env['investment.timeseries'].search(domain+[('date', '=', record.date)])
            record.predicted_position = sum(record.timeseries_ids.mapped('position'))
            record.difference = record.predicted_position - record.position
            if record.difference < 0:
                record.state = 'behind' if (record.date or today) > today else 'missed'
            else:
                record.state = 'ahead' if (record.date or today) > today else 'reached'


    @api.depends('position', 'inflation_rate', 'date')
    def _compute_real_position(self):
        reference = self.search([], limit=1)
        for record in self:
            if record.date:
                record.real_position = record.position * (1 - record.inflation_rate)**((record.date-reference.date).days/365)
            else:
                record.real_position = record.position


class InvestmentCategory(models.Model):
    _name = 'investment.category'
    _description = 'Investment Category'
    _order = 'sequence, id'


    name = fields.Char(required=True)
    sequence = fields.Integer(string='Sequence')
    liquid = fields.Boolean()

    favourite = fields.Boolean()

    def toggle_favourite(self):
        for record in self:
            record.favourite = not record.favourite


class InvestmentIntegration(models.Model):
    _name = 'investment.integration'
    _description = 'Investment Integration'

    name = fields.Char(required=True)
    code = fields.Text(required=True)

    @api.constrains('code')
    def _validate_code(self):
        for record in self:
            msg = test_python_expr(expr=record.code.strip(), mode="exec")
            if msg:
                raise ValidationError(msg)

    def execute(self, asset):
        self.ensure_one()
        globals_dict = {
            'ValidationError': ValidationError,
            'requests': requests,
            'datetime': datetime,
            'dateutil': dateutil,
            'lxml': lxml,
            'io': io,
            'pandas': pandas,
            'self': asset,
        }
        safe_eval(self.code, globals_dict=globals_dict, mode="exec", nocopy=True)


class InvestmentAsset(models.Model):
    _name = 'investment.asset'
    _description = 'Investment Asset'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'category_id, sequence, id'

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



    def _get_plan(self, date):
        self.ensure_one()
        return self.plan_ids.filtered(lambda e: e.year == date.year) or self.plan_ids.filtered(lambda e: not e.year)

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
                date += relativedelta(months=1)
                if asset_id.plan_start_date:
                    n -= 1

            end = date + relativedelta(months=n)
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
                        days = (date - (date-relativedelta(months=1))).days
                        rate = asset_id.plan_yearly_interest*(days/360)
                        interest = PV*rate
                        reduction = P-interest+asset_id.plan_fee
                        dsum = (-reduction) + (-interest) + (asset_id.plan_fee)
                        reduction_vals = {
                            'description': f'{i}: {-reduction:.2f} + {-interest:.2f} + {asset_id.plan_fee:.2f} = {dsum:.2f}',
                            'quantity': -reduction/curr_price, 'payment': abs(P), 'fee': asset_id.plan_fee, 'exchange_rate': 1}
                        tr = Transaction.create({**base_vals, **reduction_vals})
                        PV -= reduction
                    else:
                        raise ValueError(f"Invalid plan type {asset_id.plan_type}")

                price_id = Price.search([(key, '=', value) for key, value in base_vals.items()])
                if not price_id:
                    price_id = Price.create({**base_vals, **{'price': price}})
                else:
                    price_id.price = price

                date += relativedelta(months=1)


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


class InvestmentAssetPrice(models.Model):
    _name = 'investment.asset.price'
    _description = 'Asset Price'
    _order = 'time desc'
    _rec_name = 'price'


    asset_id = fields.Many2one(
        comodel_name='investment.asset',
        required=True,
        ondelete='cascade',
        index=True,
    )
    currency_id = fields.Many2one(related='asset_id.currency_id')

    price = fields.Monetary(required=True, group_operator='avg')

    time = fields.Datetime(required=True, default=fields.Datetime.now)

    prediction = fields.Boolean()

    extrapolated = fields.Boolean()

    transaction_id = fields.Many2one(
        comodel_name='investment.asset.transaction',
        index=True,
    )

    _sql_constraints = [
        ('unique_price', 'unique(asset_id, time)', 'Price for this time is already configured!'),
    ]


    def extrapolate_cagr(self):
        assert len(self) == 2, "Two prices required"
        Price = self.env['investment.asset.price']
        first, last = self.sorted('time')
        n = (last.time-first.time).days/365
        cagr = ((last.price/first.price)**(1/n) - 1)

        time = first.time
        price = first.price
        while time < (last.time - relativedelta(months=1)):
            time += relativedelta(months=1)
            price *= (1+cagr)**(1/12)
            base_vals = {
                'extrapolated': True,
                'asset_id': first.asset_id.id,
                'time': time,
            }
            price_id = Price.search([(key, '=', value) for key, value in base_vals.items()])
            if not price_id:
                price_id = Price.create({**base_vals, **{'price': price}})
            else:
                price_id.price = price






class InvestmentAssetTransaction(models.Model):
    _name = 'investment.asset.transaction'
    _description = 'Asset Transaction'
    _order = 'time desc, ttype'

    asset_id = fields.Many2one(
        comodel_name='investment.asset',
        required=True,
        ondelete='cascade',
        index=True,
    )

    currency_id = fields.Many2one(related='asset_id.company_currency_id')

    payment = fields.Monetary(required=True)

    description = fields.Char()

    exchange_rate = fields.Float(digits='Investment Asset quantity')

    fee = fields.Monetary(store=True, readonly=False,  compute='_compute_fee', inverse='_inverse_fee')

    quantity = fields.Float(digits='Investment Asset quantity')

    time = fields.Datetime(required=True, default=fields.Datetime.now)

    profit = fields.Monetary(compute='_compute_profit')

    prediction = fields.Boolean()

    category_id = fields.Many2one(related='asset_id.category_id', store=True, readonly=True)
    liquid = fields.Boolean(related='category_id.liquid', store=True, readonly=True)

    ttype = fields.Selection(
        selection=[
            ('buy', 'Buy'),
            ('sell', 'Sell'),
            ('yield', 'Yield'),
            ('cost', 'Cost'),
        ],
        string='Type',
        compute='_compute_report',
        store=True,
    )

    cash_flow = fields.Monetary(
        compute='_compute_report',
        store=True,
    )

    def _fill_daily_price(self):
        Price = self.env['investment.asset.price']
        for transaction in self:
            start_time = transaction.time.replace(hour=0, minute=0, microsecond=0)
            stop_time = transaction.time.replace(hour=23, minute=59, microsecond=0)
            exists = Price.search([('time', '>=', start_time),('time', '<=', stop_time),('asset_id', '=', transaction.asset_id.id),('prediction', '=', False)])
            if transaction.exchange_rate and transaction.quantity and not exists:
                Price.create({
                    'time': start_time.replace(hour=12),
                    'asset_id': transaction.asset_id.id,
                    'price': transaction.exchange_rate,
                    'transaction_id': transaction.id,
                })
                _logger.info("%s (%s): %s", transaction.asset_id.name, transaction.time, transaction.exchange_rate)



    @api.depends('payment', 'quantity')
    def _compute_report(self):
        for record in self:
            if record.quantity > 0:
                record.ttype = 'buy'
                record.cash_flow = record.payment
            elif record.quantity < 0:
                record.ttype = 'sell'
                record.cash_flow = -record.payment
            elif record.payment > 0:
                record.ttype = 'yield'
                record.cash_flow = -record.payment
            elif record.payment < 0:
                record.ttype = 'cost'
                record.cash_flow = -record.payment # cost has a negative cashflow which needs to be flipped to positive as payment.
            else:
                record.ttype = False
                record.cash_flow = False
                _logger.error("Invalid type: %s", record)




    @api.depends('payment', 'quantity', 'asset_id.last_price')
    def _compute_profit(self):
        for tx in self:
            quantity = tx.quantity
            if not quantity: # if quantity is 0, the cash flow will be profit.
                tx.profit = tx.payment
            else:
                tx.profit = (tx.asset_id.last_price - (tx.payment / abs(quantity))) * quantity


    @api.depends('exchange_rate', 'payment', 'quantity')
    def _compute_fee(self):
        for tx in self:
            quantity = abs(tx.quantity)
            if not (quantity and tx.payment and tx.exchange_rate):
                tx.fee = 0.0
            else:
                tx.fee = (tx.payment/quantity - tx.exchange_rate) * quantity

    def _inverse_fee(self):
        for tx in self:
            quantity = abs(tx.quantity)
            if not (quantity and tx.payment and tx.exchange_rate):
                tx.exchange_rate = 0.0
            else:
                tx.exchange_rate = (tx.payment/quantity - tx.fee/quantity)


class InvestmentAssetRealized(models.Model):
    _name = 'investment.asset.realized'
    _description = 'Asset Realized'
    _order = 'sell_date desc, buy_date desc'

    asset_id = fields.Many2one(
        comodel_name='investment.asset',
        required=True,
        ondelete='cascade',
        index=True,
    )

    currency_id = fields.Many2one(related='asset_id.company_currency_id')
    category_id = fields.Many2one(related='asset_id.category_id', store=True)

    sell_batch_id = fields.Many2one(
        comodel_name='investment.asset.transaction',
        required=True,
        ondelete='cascade',
        index=True,
    )

    buy_batch_id = fields.Many2one(
        comodel_name='investment.asset.transaction',
        required=True,
        ondelete='cascade',
        index=True,
    )

    quantity = fields.Float(digits='Investment Asset quantity')

    sell_price = fields.Monetary(compute='_compute_profit', store=True)
    sell_date = fields.Date(compute='_compute_profit', store=True)
    sell_fee = fields.Monetary(compute='_compute_profit', store=True)
    buy_price = fields.Monetary(compute='_compute_profit', store=True)
    buy_date = fields.Date(compute='_compute_profit', store=True)
    buy_fee = fields.Monetary(compute='_compute_profit', store=True)
    profit = fields.Monetary(string='Profit/Loss', compute='_compute_profit', store=True)


    def _compute_profit(self):
        for record in self:
            record.sell_date = record.sell_batch_id.time.date()
            record.sell_fee = record.sell_batch_id.fee * (record.quantity / abs(record.sell_batch_id.quantity))
            record.sell_price = (record.sell_batch_id.exchange_rate) * record.quantity

            record.buy_date = record.buy_batch_id.time.date()
            record.buy_fee = record.buy_batch_id.fee * (record.quantity / abs(record.buy_batch_id.quantity))
            record.buy_price = (record.buy_batch_id.exchange_rate) * record.quantity

            record.profit = record.sell_price - record.sell_fee - record.buy_price - record.buy_fee


    _sql_constraints = [
        ('unique_realized', 'UNIQUE(sell_batch_id, buy_batch_id)', 'A realization for this aquisition/sell link already exists!'),
    ]
