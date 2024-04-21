# -*- coding: utf-8 -*-

from odoo import api, models, fields, _
import logging



_logger = logging.getLogger(__name__)





class InvestmentPositionTransaction(models.Model):
    _name = 'investment.position.transaction'
    _description = 'Position Transaction'
    _inherit = ['mail.thread']
    _order = 'time desc, ttype'

    position_id = fields.Many2one(
        comodel_name='investment.position',
        required=True,
        ondelete='cascade',
        index=True,
        tracking=True,
    )

    asset_id = fields.Many2one(related='position_id.asset_id')

    currency_id = fields.Many2one(related='position_id.currency_id')
    company_currency_id = fields.Many2one(related='position_id.company_currency_id')
    company_id = fields.Many2one(related='position_id.company_id')

    payment = fields.Monetary(required=True, currency_field='company_currency_id', tracking=True)

    description = fields.Char()

    exchange_rate = fields.Float(digits='Investment Asset quantity', tracking=True)

    currency_rate_id = fields.Many2one(
        comodel_name='res.currency.rate',
        compute='_compute_currency_rate_id',
        store=True,
        readonly=False,
    )

    fee = fields.Monetary(readonly=False,  compute='_compute_fee', inverse='_inverse_fee', currency_field='company_currency_id')

    quantity = fields.Float(digits='Investment Asset quantity', tracking=True)

    time = fields.Datetime(required=True, default=fields.Datetime.now, tracking=True)

    profit = fields.Monetary(compute='_compute_profit', currency_field='company_currency_id')

    prediction = fields.Boolean(
        compute='_compute_prediction',
        inverse='_inverse_prediction',
        store=True,
        tracking=True,
    )

    usage = fields.Selection(
        selection=[
            ('record', 'Record'),
            ('prediction', 'Prediction'),
            ('realized', 'Realized Calculation'),
        ],
        required=True,
        default='record',
        tracking=True,
    )

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
        tracking=True,
    )

    cash_flow = fields.Monetary(
        compute='_compute_report',
        store=True,
        currency_field='company_currency_id'
    )


    _sql_constraints = [
        ('check_exchange_rate', "CHECK(payment = 0 OR exchange_rate <> 0 OR ttype not in ('buy', 'sell'))", "A buy/sell transaction can not be encoded without an exchange rate."),
    ]

    @api.depends('usage')
    def _compute_prediction(self):
        for record in self: record.prediction = record.usage == 'prediction'

    def _inverse_prediction(self):
        for record in self: record.usage = 'prediction' if record.prediction else 'record'

    def _fill_daily_price(self):
        Price = self.env['investment.asset.price']
        for transaction in self:
            start_time = transaction.time.replace(hour=0, minute=0, microsecond=0)
            stop_time = transaction.time.replace(hour=23, minute=59, microsecond=0)
            exists = Price.search([('time', '>=', start_time),('time', '<=', stop_time),('asset_id', '=', transaction.asset_id.id),('prediction', '=', False)])
            if transaction.exchange_rate and transaction.quantity and not exists:
                price = transaction.currency_id._convert(
                    from_amount=transaction.exchange_rate,
                    to_currency=transaction.company_currency_id,
                    company=transaction.company_id,
                    date=transaction.time,
                )
                Price.create({
                    'time': start_time.replace(hour=12),
                    'asset_id': transaction.position_id.asset_id.id,
                    'price': price,
                    'transaction_id': transaction.id,
                })
                _logger.info("%s (%s): %s", transaction.asset_id.name, transaction.time, price)



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


    @api.depends('currency_id', 'time')
    def _compute_currency_rate_id(self):
        for tx in self:
            if tx.currency_id != tx.company_currency_id:
                tx.currency_rate_id = tx.env['res.currency.rate'].search([
                    ('currency_id', '=', tx.currency_id.id),
                    ('company_id', '=', tx.company_id.id),
                    ('name', '=', tx.time.date()),
                ]) or tx.env['res.currency.rate'].create({
                    'currency_id': tx.currency_id.id,
                    'name': tx.time.date(),
                    'rate': 1.0,
                    'company_id': tx.company_id.id,
                })


    @api.depends('payment', 'quantity', 'position_id.last_price_own_currency')
    def _compute_profit(self):
        for tx in self:
            quantity = tx.quantity
            if not quantity: # if quantity is 0, the cash flow will be profit.
                tx.profit = tx.payment
            else:
                tx.profit = (tx.position_id.last_price_own_currency - (tx.payment / abs(quantity))) * quantity


    @api.depends('exchange_rate', 'payment', 'quantity', 'time', 'currency_rate_id.rate')
    def _compute_fee(self):
        for tx in self:
            quantity = abs(tx.quantity)
            if not (quantity and tx.payment and tx.exchange_rate):
                tx.fee = 0.0
            else:
                cmp_exchange_rate = tx.exchange_rate
                if tx.currency_rate_id:
                    cmp_exchange_rate *= tx.currency_rate_id.inverse_company_rate

                tx.fee = (tx.payment/quantity - cmp_exchange_rate) * quantity

    def _inverse_fee(self):
        for tx in self:
            quantity = abs(tx.quantity)
            if not (quantity and tx.payment and tx.exchange_rate):
                tx.exchange_rate = 0.0
            else:
                cmp_fee = tx.fee
                if tx.currency_rate_id:
                    cmp_fee *= tx.currency_rate_id.company_rate

                cmp_payment = tx.payment
                if tx.currency_rate_id:
                    cmp_payment *= tx.currency_rate_id.company_rate

                tx.exchange_rate = (cmp_payment/quantity - cmp_fee/quantity)


