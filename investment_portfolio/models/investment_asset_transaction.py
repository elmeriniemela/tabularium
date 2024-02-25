# -*- coding: utf-8 -*-

from odoo import api, models, fields, _
import logging



_logger = logging.getLogger(__name__)





class InvestmentAssetTransaction(models.Model):
    _name = 'investment.asset.transaction'
    _description = 'Asset Transaction'
    _order = 'time desc, ttype'

    position_id = fields.Many2one(
        comodel_name='investment.position',
        required=True,
        ondelete='cascade',
        index=True,
    )

    asset_id = fields.Many2one(related='position_id.asset_id')

    currency_id = fields.Many2one(related='position_id.company_currency_id')

    payment = fields.Monetary(required=True)

    description = fields.Char()

    exchange_rate = fields.Float(digits='Investment Asset quantity')

    fee = fields.Monetary(store=True, readonly=False,  compute='_compute_fee', inverse='_inverse_fee')

    quantity = fields.Float(digits='Investment Asset quantity')

    time = fields.Datetime(required=True, default=fields.Datetime.now)

    profit = fields.Monetary(compute='_compute_profit')

    prediction = fields.Boolean(
        compute='_compute_prediction',
        inverse='_inverse_prediction',
        store=True,
    )

    usage = fields.Selection(
        selection=[
            ('record', 'Record'),
            ('prediction', 'Prediction'),
            ('realized', 'Realized Calculation'),
        ],
        required=True,
        default='record',
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
    )

    cash_flow = fields.Monetary(
        compute='_compute_report',
        store=True,
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




    @api.depends('payment', 'quantity', 'position_id.last_price')
    def _compute_profit(self):
        for tx in self:
            quantity = tx.quantity
            if not quantity: # if quantity is 0, the cash flow will be profit.
                tx.profit = tx.payment
            else:
                tx.profit = (tx.position_id.last_price - (tx.payment / abs(quantity))) * quantity


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


