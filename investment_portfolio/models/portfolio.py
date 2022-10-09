# -*- coding: utf-8 -*-

from odoo import api, models, fields, _
from odoo.exceptions import ValidationError
from odoo.tools import float_is_zero, float_compare
from odoo.osv import expression
import traceback, logging
from dateutil.relativedelta import relativedelta
import random

from odoo.tools.safe_eval import safe_eval, test_python_expr, wrap_module, datetime, dateutil

import lxml
lxml_mods = ['etree']
for mod in lxml_mods:
    __import__('lxml.%s' % mod)
lxml = wrap_module(__import__('lxml'), {mod: getattr(lxml, mod).__all__ for mod in lxml_mods})

requests = wrap_module(__import__('requests'), ['get', 'post'])
io = wrap_module(__import__('io'), ['StringIO', 'BytesIO'])


_logger = logging.getLogger(__name__)

class Currency(models.Model):
    _inherit = 'res.currency'

    def cron_update_rate(self, mode='intraday'):
        Rate = self.env['res.currency.rate']
        Asset = self.env['investment.asset']
        currencies = {c.name: c for c in self.search([])}
        from_currency = self.env.company.currency_id.name
        api_key = self.env['ir.config_parameter'].sudo().get_param('alpha.vantage.api.key')
        for to_currency, currency_id in currencies.items():
            _logger.info(f"Update {mode} rates on {to_currency}")
            rates = {}
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
            elif mode == 'weekly':
                resp = requests.get(f'https://www.alphavantage.co/query?function=FX_WEEKLY&from_symbol={from_currency}&to_symbol={to_currency}&apikey={api_key}')
                vals = resp.json()["Time Series FX (Weekly)"]
                rates = {dateutil.parser.parse(d_str).date(): float(w['4. close']) for d_str, w in vals.items() }
            else:
                raise ValidationError(f"Invalid {mode=}")

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

    buy_total = fields.Monetary(compute='_compute_aggregate', store=True, currency_field='company_currency_id')
    sell_total = fields.Monetary(compute='_compute_aggregate', store=True, currency_field='company_currency_id')
    position = fields.Monetary(compute='_compute_aggregate', store=True, currency_field='company_currency_id')

    avg_buy_price = fields.Monetary(compute='_compute_aggregate', store=True, currency_field='company_currency_id')
    avg_sell_price = fields.Monetary(compute='_compute_aggregate', store=True, currency_field='company_currency_id')


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

    is_monday = fields.Boolean(
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
            if record.date.month == 1 and record.date.day == 1:
                record.granularity = '1_yearly'
            elif record.date.month % 4 == 0 and record.date.day == 1:
                record.granularity = '2_quaterly'
            elif record.date.day == 1:
                record.granularity = '3_monthly'
            else:
                record.granularity = '4_daily'

            record.is_monday = record.date.isoweekday() == 1


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
            'week': [('is_monday', '=', True)],
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

            record.update(record.asset_id._get_position(record.last_price, record.transaction_ids))




    @api.model
    def cron_create_time_series(self):
        Price = self.env['investment.asset.price']
        Transaction = self.env['investment.asset.transaction']
        today = datetime.date.today()

        # Remove old predictions.
        Price.search([('prediction', '=', True),('time', '<', today)]).unlink()
        Transaction.search([('prediction', '=', True)]).unlink()


        precision = self.env['decimal.precision'].precision_get('Investment Asset quantity')
        predict_years = int(self.env['ir.config_parameter'].sudo().get_param('investment_portfolio.predict_years', '25'))

        existing = {(p.asset_id.id, p.date): p for p in self.search([])}

        recompute = self.browse()


        for asset_id in self.env['investment.asset'].search([]):
            first = self.env['investment.asset.transaction'].search([('asset_id', '=', asset_id.id)], order='time asc', limit=1)
            if not first:
                _logger.info(f"No transactions on {asset_id.name}")
                continue
            date = first.time.date()
            _logger.info(f"Make time series for {asset_id.name} starting from {date}")

            while date <= today + relativedelta(years=predict_years):
                prediction = bool(date > today)
                if prediction and float_is_zero(asset_id.quantity, precision_digits=precision):
                    break
                if prediction:
                    expectation = asset_id._get_expectation(date)
                    if not expectation:
                        _logger.info("No expectations for %s %s", asset_id.name, date)
                        break
                    previous_price *= (1+expectation.yearly_return)
                    base_vals = {
                        'prediction': True,
                        'asset_id': asset_id.id,
                        'time': date,
                    }
                    if expectation.savings:
                        transaction_id = Transaction.search([(key, '=', value) for key, value in base_vals.items()])
                        quantity = expectation.savings/previous_price
                        if date.year-1 == today.year:
                            months = 12-today.month
                            _logger.info("Only %s months of %s left to predict.", months, today.year)
                        else:
                            months = 12
                        update = {'quantity': quantity*months, 'cash_flow': expectation.savings*months, 'exchange_rate': previous_price}
                        if not transaction_id:
                            transaction_id = Transaction.create({**base_vals, **update})
                        else:
                            transaction_id.update(update)

                    price_id = Price.search([(key, '=', value) for key, value in base_vals.items()])
                    if not price_id:
                        price_id = Price.create({**base_vals, **{'price': previous_price}})
                    else:
                        price_id.price = previous_price

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
                    previous_price = serie_today.price_id.price

                if prediction or date == today:
                    date += relativedelta(years=1)
                    date = date.replace(month=1, day=1)
                else:
                    date += datetime.timedelta(days=1)

            yesterday = datetime.date.today() - relativedelta(days=1)
            recompute += existing[(asset_id.id, yesterday)]

        recompute._compute_aggregate()




class InvestmentMilestone(models.Model):
    _name = 'investment.milestone'
    _description = 'Investment Milestone'
    _order = 'date asc'

    name = fields.Char(required=True)

    date = fields.Date(required=True)

    domain = fields.Text(default="[('liquid', '=', True)]", required=True)

    position = fields.Monetary(required=True, currency_field='company_currency_id')

    inflation_rate = fields.Float(default=0.07)

    real_position = fields.Monetary(compute='_compute_real_position', currency_field='company_currency_id')

    company_id = fields.Many2one(comodel_name='res.company', required=True, default=lambda self: self.env.company)

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

    timeseries_ids = fields.Many2many(
        comodel_name='investment.timeseries',
        compute='_compute_state',
    )

    @api.depends('position', 'date')
    def _compute_state(self):
        today = fields.Date.today()
        for record in self:
            domain = safe_eval(record.domain)
            record.timeseries_ids = record.env['investment.timeseries'].search(domain+[('date', '=', record.date)])
            if sum(record.timeseries_ids.mapped('position')) < record.position:
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

    name = fields.Char(required=True)
    liquid = fields.Boolean()


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
            'self': asset,
        }
        safe_eval(self.code, globals_dict=globals_dict, mode="exec", nocopy=True)


class InvestmentAssetExpectation(models.Model):
    _name = 'investment.asset.expectation'
    _description = 'Investment Expectation'

    asset_id = fields.Many2one(
        comodel_name='investment.asset',
        required=True,
        ondelete='cascade',
    )
    currency_id = fields.Many2one(related='asset_id.company_currency_id')

    yearly_return = fields.Float(group_operator='avg')

    savings = fields.Monetary(string="Monthly savings")

    year = fields.Integer()

    _sql_constraints = [
        ('unique_expectation', 'unique(asset_id, year)', 'Expectation for this year is already configured!'),
    ]

    def copy(self, default=None):
        default = default or {'year': self.year+1}
        return super().copy(default)

    def copy_button(self):
        self.ensure_one()
        self.copy()


class InvestmentAsset(models.Model):
    _name = 'investment.asset'
    _description = 'Investment Asset'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(required=True)

    ticker = fields.Char(required=True)

    notes = fields.Text()

    color = fields.Char(required=True, default=lambda self: self._get_random_color())

    company_id = fields.Many2one(comodel_name='res.company', required=True, default=lambda self: self.env.company)

    category_id = fields.Many2one(comodel_name='investment.category', required=True)
    liquid = fields.Boolean(related='category_id.liquid', store=True, readonly=True)

    company_currency_id = fields.Many2one(related='company_id.currency_id', string="Company Currency")

    currency_id = fields.Many2one(
        comodel_name='res.currency',
        required=True,
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


    quantity = fields.Float(compute='_compute_aggregate', store=True, digits='Investment Asset quantity', group_operator=None)

    buy_total = fields.Monetary(compute='_compute_aggregate', store=True, currency_field='company_currency_id')
    sell_total = fields.Monetary(compute='_compute_aggregate', store=True, currency_field='company_currency_id')
    position = fields.Monetary(compute='_compute_aggregate', store=True, currency_field='company_currency_id')

    avg_buy_price = fields.Monetary(compute='_compute_aggregate', store=True, currency_field='company_currency_id')
    avg_sell_price = fields.Monetary(compute='_compute_aggregate', store=True, currency_field='company_currency_id')


    last_update = fields.Datetime(compute='_compute_aggregate', store=True)
    last_price = fields.Monetary(compute='_compute_aggregate', store=True, currency_field='company_currency_id', group_operator=None)
    profit = fields.Monetary(compute='_compute_aggregate', store=True, currency_field='company_currency_id', group_operator='sum')
    profit_percent = fields.Float(compute='_compute_aggregate', store=True, group_operator='avg')
    daily_price = fields.Float(compute='_compute_aggregate', store=True, group_operator='avg')
    weekly_price = fields.Float(compute='_compute_aggregate', store=True, group_operator='avg')
    monthly_price = fields.Float(compute='_compute_aggregate', store=True, group_operator='avg')
    ytd_price = fields.Float(compute='_compute_aggregate', store=True, group_operator='avg')

    integration_id = fields.Many2one(comodel_name='investment.integration')

    integration_error_id = fields.Many2one(
        comodel_name='mail.activity',
        copy=False,
    )


    is_cash = fields.Boolean(
        compute='_compute_is_cash',
    )

    expectation_ids = fields.One2many(
        comodel_name='investment.asset.expectation',
        inverse_name='asset_id',
        default=lambda self: [(0, 0, {'yearly_return': 0.1})]
    )


    def _get_expectation(self, date):
        self.ensure_one()
        return self.expectation_ids.filtered(lambda e: e.year == date.year) or self.expectation_ids.filtered(lambda e: not e.year)


    def _get_random_color(self):
        rgb = lambda: random.randint(0,255)
        return f'rgba({rgb()},{rgb()},{rgb()},1)'

    def random_color(self):
        for record in self:
            record.color = record._get_random_color()

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
                num = 0.0
                denom = 0.0
                for asset in assets:
                    num += (asset.sell_total-asset.buy_total)
                    denom += asset.buy_total
                if denom:
                    line['profit_percent'] = num / denom
        return res


    def _compute_is_cash(self):
        currency_ticker = self.env.company.currency_id.name
        for record in self:
            record.is_cash = record.ticker == currency_ticker

    @api.depends(
        'transaction_ids',
        'transaction_ids.quantity',
        'transaction_ids.cash_flow',
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

            closing_price = closing_price_id.currency_id._convert(
                from_amount=closing_price_id.price or 0.0,
                to_currency=record.company_currency_id,
                company=record.env.company,
                date=closing_price_id.time or fields.Datetime.now(),
            )
            return (market_price-closing_price)/closing_price if closing_price else 0.0


        for record in self:
            price_id = record.price_ids.sorted()[:1]
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
            record.ytd_price = percent_change(record, fields.Datetime.now().replace(day=1, month=1, hour=0, minute=0, second=0), record.last_price)


    def _get_position(self, market_price, transaction_ids):
        self.ensure_one()
        quantity = 0.0
        buy_total = 0.0
        sell_total = 0.0

        buy_volume = 0
        sell_volume = 0

        for tx in transaction_ids:
            quantity += tx.quantity
            cash_flow = tx.cash_flow
            if tx.quantity > 0:
                buy_total += cash_flow
                buy_volume += abs(tx.quantity)
            else: # Dividends should have 0.0 quantity and they fall here, increasing profit.
                sell_total += cash_flow
                sell_volume += abs(tx.quantity)

        sell_total += quantity * market_price
        sell_volume += quantity
        return {
            'position': quantity * market_price,
            'quantity': quantity,
            'buy_total': buy_total,
            'sell_total': sell_total,
            'avg_buy_price': buy_total/buy_volume if buy_volume else 0.0,
            'avg_sell_price': sell_total/sell_volume if sell_volume else 0.0,
            'profit': sell_total - buy_total,
            'profit_percent': (sell_total-buy_total) / buy_total if buy_total else 0.0,
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





class InvestmentAssetPrice(models.Model):
    _name = 'investment.asset.price'
    _description = 'Asset Price'
    _order = 'time desc'
    _rec_name = 'price'


    asset_id = fields.Many2one(
        comodel_name='investment.asset',
        required=True,
        ondelete='cascade',
    )
    currency_id = fields.Many2one(related='asset_id.currency_id')

    price = fields.Monetary(required=True, group_operator='avg')

    time = fields.Datetime(required=True, default=fields.Datetime.now)

    prediction = fields.Boolean()

    transaction_id = fields.Many2one(
        comodel_name='investment.asset.transaction',
    )

    _sql_constraints = [
        ('unique_price', 'unique(asset_id, time)', 'Price for this time is already configured!'),
    ]



class InvestmentAssetPrice(models.Model):
    _name = 'investment.asset.transaction'
    _description = 'Asset Transaction'
    _order = 'time desc'

    asset_id = fields.Many2one(
        comodel_name='investment.asset',
        required=True,
        ondelete='cascade',
    )

    currency_id = fields.Many2one(related='asset_id.company_currency_id')

    cash_flow = fields.Monetary(required=True)

    description = fields.Char()

    exchange_rate = fields.Monetary()

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

    payment_or_refund = fields.Monetary(
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



    @api.depends('cash_flow', 'quantity')
    def _compute_report(self):
        for record in self:
            if record.quantity > 0:
                record.ttype = 'buy'
                record.payment_or_refund = record.cash_flow
            elif record.quantity < 0:
                record.ttype = 'sell'
                record.payment_or_refund = -record.cash_flow
            elif record.cash_flow > 0:
                record.ttype = 'yield'
                record.payment_or_refund = -record.cash_flow
            elif record.cash_flow < 0:
                record.ttype = 'cost'
                record.payment_or_refund = -record.cash_flow # cost has a negative cashflow which needs to be flipped to positive as payment.
            else:
                record.ttype = False
                record.payment_or_refund = False
                _logger.error("Invalid type: %s", record)




    @api.depends('cash_flow', 'quantity')
    def _compute_profit(self):
        for tx in self:
            quantity = tx.quantity
            if not quantity: # if quantity is 0, the cash flow will be profit.
                tx.profit = tx.cash_flow
            else:
                tx.profit = (tx.asset_id.last_price - (tx.cash_flow / abs(quantity))) * quantity

    @api.onchange('cash_flow', 'quantity')
    def _onchange_amount(self):
        for tx in self:
            if not (tx.exchange_rate and tx.fee):
                tx.fee = 0.0


    @api.depends('exchange_rate')
    def _compute_fee(self):
        for tx in self:
            quantity = abs(tx.quantity)
            if not quantity:
                tx.fee = 0.0
            else:
                tx.fee = (tx.cash_flow/quantity - tx.exchange_rate) * quantity

    def _inverse_fee(self):
        for tx in self:
            quantity = abs(tx.quantity)
            if not quantity:
                tx.exchange_rate = 0.0
            else:
                tx.exchange_rate = (tx.cash_flow/quantity - tx.fee/quantity)