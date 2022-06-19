# -*- coding: utf-8 -*-

from odoo import api, models, fields, _
from odoo.exceptions import ValidationError

class InvestmentAsset(models.Model):
    _name = 'investment.asset'
    _description = 'Investment Asset'

    name = fields.Char(required=True)

    ticker = fields.Char(required=True)

    notes = fields.Text()


    company_id = fields.Many2one(comodel_name='res.company', required=True, default=lambda self: self.env.company)

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


    quantity = fields.Float(compute='_compute_quantity', digits='Investment Asset quantity')
    value = fields.Monetary(compute='_compute_value', currency_field='company_currency_id', store=True)


    @api.depends('transaction_ids.quantity')
    def _compute_quantity(self):
        for record in self:
            record.quantity = sum(record.transaction_ids.mapped('quantity'))

    @api.depends('price_ids.price', 'quantity', 'currency_id', 'company_currency_id')
    def _compute_value(self):
        for record in self:
            last = record.price_ids[:1]
            if not last:
                record.value = 0.0
            else:
                record.value = record.quantity * record.currency_id._convert(
                    from_amount=last.price,
                    to_currency=record.company_currency_id,
                    company=self.env.company,
                    date=last.time,
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

    price = fields.Monetary(required=True)

    time = fields.Datetime(required=True, default=fields.Datetime.now)


class InvestmentAssetPrice(models.Model):
    _name = 'investment.asset.transaction'
    _description = 'Investment Asset Price'
    _order = 'time desc'

    asset_id = fields.Many2one(
        comodel_name='investment.asset',
        required=True,
        ondelete='cascade',
    )
    currency_id = fields.Many2one(related='asset_id.currency_id')

    cash_flow = fields.Monetary(required=True)

    exchange_rate = fields.Monetary()
    fee = fields.Monetary(store=True, readonly=False,  compute='_compute_fee', inverse='_inverse_fee')

    quantity = fields.Float(digits='Investment Asset quantity')

    time = fields.Datetime(required=True, default=fields.Datetime.now)

    _sql_constraints = [
        ('cash_flow_positive', 'CHECK (cash_flow > 0)', 'Cash flow must be greater than zero! Use negative quantity if needed.'),
    ]


    @api.onchange('cash_flow', 'quantity')
    def _onchange_amount(self):
        for record in self:
            quantity = abs(record.quantity)
            if not (record.exchange_rate and record.fee):
                record.exchange_rate = (record.cash_flow / quantity if quantity else 0.0)


    @api.depends('exchange_rate')
    def _compute_fee(self):
        for record in self:
            quantity = abs(record.quantity)
            if not quantity:
                record.fee = 0.0
            else:
                record.fee = (record.cash_flow/quantity - record.exchange_rate) * quantity

    def _inverse_fee(self):
        for record in self:
            quantity = abs(record.quantity)
            if not quantity:
                record.exchange_rate = 0.0
            else:
                record.exchange_rate = (record.cash_flow/quantity - record.fee/quantity)