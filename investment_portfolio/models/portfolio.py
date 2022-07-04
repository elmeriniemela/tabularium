# -*- coding: utf-8 -*-

from odoo import api, models, fields, _
from odoo.exceptions import ValidationError
import requests, datetime, traceback, logging, dateutil, lxml.etree, io
from odoo.tools.safe_eval import safe_eval, test_python_expr
from odoo.tools import float_is_zero, float_compare


_logger = logging.getLogger(__name__)

class Currency(models.Model):
    _inherit = 'res.currency'

    def cron_update_rate(self, mode='realtime'):
        Rate = self.env['res.currency.rate']
        Asset = self.env['investment.asset']
        currencies = {c.name: c for c in self.search([])}
        from_currency = self.env.company.currency_id.name
        api_key = self.env['ir.config_parameter'].sudo().get_param('alpha.vantage.api.key')
        for to_currency, currency_id in currencies.items():


            rates = {}
            if mode == 'realtime':
                resp = requests.get(f'https://www.alphavantage.co/query?function=CURRENCY_EXCHANGE_RATE&from_currency={from_currency}&to_currency={to_currency}&apikey={api_key}')
                vals = resp.json()["Realtime Currency Exchange Rate"]
                rates = {dateutil.parser.parse(vals['6. Last Refreshed']).date(): float(vals['5. Exchange Rate'])}
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



class InvestmentGategory(models.Model):
    _name = 'investment.category'
    _description = 'Investment Category'

    name = fields.Char(required=True)

class InvestmentGategory(models.Model):
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

class InvestmentAsset(models.Model):
    _name = 'investment.asset'
    _description = 'Investment Asset'
    _inherit = ['mail.thread']

    name = fields.Char(required=True)

    ticker = fields.Char(required=True)

    notes = fields.Text()


    company_id = fields.Many2one(comodel_name='res.company', required=True, default=lambda self: self.env.company)

    category_id = fields.Many2one(comodel_name='investment.category', required=True)

    company_currency_id = fields.Many2one(related='company_id.currency_id', string="Company Currency")

    currency_id = fields.Many2one(
        comodel_name='res.currency',
        required=True,
    )

    price_ids = fields.One2many(
        comodel_name='investment.asset.price',
        inverse_name='asset_id',
    )

    transaction_ids = fields.One2many(
        comodel_name='investment.asset.transaction',
        inverse_name='asset_id',
    )


    quantity = fields.Float(compute='_compute_aggregate', store=True, digits='Investment Asset quantity')
    is_closed = fields.Boolean(compute='_compute_aggregate', store=True)

    buy_total = fields.Monetary(compute='_compute_aggregate', store=True, currency_field='company_currency_id')
    sell_total = fields.Monetary(compute='_compute_aggregate', store=True, currency_field='company_currency_id')
    position = fields.Monetary(compute='_compute_aggregate', store=True, currency_field='company_currency_id')

    avg_buy_price = fields.Monetary(compute='_compute_aggregate', store=True, currency_field='company_currency_id')
    avg_sell_price = fields.Monetary(compute='_compute_aggregate', store=True, currency_field='company_currency_id')


    last_price = fields.Monetary(compute='_compute_aggregate', store=True, currency_field='company_currency_id')
    profit = fields.Monetary(compute='_compute_aggregate', store=True, currency_field='company_currency_id', group_operator='sum')
    profit_percent = fields.Float(compute='_compute_aggregate', store=True, currency_field='company_currency_id', group_operator='avg')

    integration_id = fields.Many2one(comodel_name='investment.integration')

    _sql_constraints = [
        ('ticker_unique', 'unique(ticker)', 'Ticker already exists!'),
    ]


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
        precision = self.env['decimal.precision'].precision_get('Investment Asset quantity')
        for record in self:
            prices = record.price_ids.sorted()
            last = prices[:1]
            record.last_price = record.currency_id._convert(
                from_amount=last.price or 0.0,
                to_currency=record.company_currency_id,
                company=self.env.company,
                date=last.time or fields.Datetime.now(),
            )


            quantity = 0.0
            buy_total = 0.0
            sell_total = 0.0

            buy_volume = 0
            sell_volume = 0

            for tx in record.transaction_ids:
                quantity += tx.quantity
                cash_flow = tx.cash_flow
                if tx.quantity > 0:
                    buy_total += cash_flow
                    buy_volume += abs(tx.quantity)
                else: # Dividends should have 0.0 quantity and they fall here, increasing profit.
                    sell_total += cash_flow
                    sell_volume += abs(tx.quantity)

            sell_total += quantity * record.last_price
            sell_volume += quantity

            record.is_closed = float_is_zero(quantity, precision_digits=precision)
            record.position = quantity * record.last_price
            record.quantity = quantity
            record.buy_total = buy_total
            record.sell_total = sell_total
            record.avg_buy_price = buy_total/buy_volume if buy_volume else 0.0
            record.avg_sell_price = sell_total/sell_volume if sell_volume else 0.0
            record.profit = record.sell_total - record.buy_total
            record.profit_percent = (record.avg_sell_price-record.avg_buy_price) / record.avg_buy_price if record.avg_buy_price else 0.0


    def run_integration(self):
        for asset in self:
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
                asset.message_post(
                    body=traceback.format_exc().replace('\n', '<br/>'),
                    subtype='mail.mt_comment',
                )





class InvestmentAssetPrice(models.Model):
    _name = 'investment.asset.price'
    _description = 'Investment Asset Price'
    _order = 'time desc'

    asset_id = fields.Many2one(
        comodel_name='investment.asset',
        required=True,
        ondelete='cascade',
    )
    currency_id = fields.Many2one(related='asset_id.currency_id')

    price = fields.Monetary(required=True, group_operator='avg')

    time = fields.Datetime(required=True, default=fields.Datetime.now)

    _sql_constraints = [
        ('unique_price', 'unique(asset_id, time)', 'Price for this time is already configured!'),
    ]



class InvestmentAssetPrice(models.Model):
    _name = 'investment.asset.transaction'
    _description = 'Investment Asset Price'
    _order = 'time desc'

    asset_id = fields.Many2one(
        comodel_name='investment.asset',
        required=True,
        ondelete='cascade',
    )

    currency_id = fields.Many2one(related='asset_id.company_currency_id')

    cash_flow = fields.Monetary(required=True)

    exchange_rate = fields.Monetary()

    fee = fields.Monetary(store=True, readonly=False,  compute='_compute_fee', inverse='_inverse_fee')

    cash_balance = fields.Boolean(default=True)
    cash_balance_id = fields.Many2one(comodel_name='investment.asset.transaction', ondelete='cascade')

    quantity = fields.Float(digits='Investment Asset quantity')

    time = fields.Datetime(required=True, default=fields.Datetime.now)

    profit = fields.Monetary(compute='_compute_profit')

    _sql_constraints = [
        ('cash_flow_positive', 'CHECK (cash_flow > 0)', 'Cash flow must be greater than zero! Use negative quantity if needed.'),
        ('quantity_non_zero', 'CHECK (1 != 0)', "Deprecated"),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        cash_asset = self.env['investment.asset'].search([('ticker', '=', self.env.company.currency_id.name)])
        for record in records:
            if record.cash_balance and cash_asset and record.asset_id != cash_asset:
                # Opposite sign for cash asset flow
                quantity = record.cash_flow if record.quantity < 0 else record.cash_flow * -1
                cash_asset.transaction_ids = [(0, 0, {
                    'quantity': quantity,
                    'cash_flow': record.cash_flow,
                    'exchange_rate': 1.0,
                    'cash_balance_id': record.id,
                    'fee': 0.0,
                })]
        return records


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