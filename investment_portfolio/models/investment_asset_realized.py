# -*- coding: utf-8 -*-

from odoo import api, models, fields, _

class InvestmentAssetRealized(models.Model):
    _name = 'investment.asset.realized'
    _description = 'Asset Realized'
    _order = 'sell_date desc, buy_date desc'

    position_id = fields.Many2one(
        comodel_name='investment.position',
        required=True,
        ondelete='cascade',
        index=True,
    )

    currency_id = fields.Many2one(related='position_id.company_currency_id')
    company_id = fields.Many2one(related='position_id.company_id')
    category_id = fields.Many2one(related='position_id.asset_id.category_id', store=True)
    portfolio_id = fields.Many2one(related='position_id.portfolio_id', store=True)

    sell_batch_id = fields.Many2one(
        comodel_name='investment.position.transaction',
        required=True,
        ondelete='cascade',
        index=True,
    )

    buy_batch_id = fields.Many2one(
        comodel_name='investment.position.transaction',
        required=True,
        ondelete='cascade',
        index=True,
    )

    quantity = fields.Float(digits='Investment Asset quantity')
    simulated = fields.Boolean(compute='_compute_simulated', store=True)

    sell_price = fields.Monetary(compute='_compute_profit', store=True, group_operator=None)
    sell_date = fields.Date(compute='_compute_profit', store=True)
    sell_fee = fields.Monetary(compute='_compute_profit', store=True)
    buy_price = fields.Monetary(compute='_compute_profit', store=True, group_operator=None)
    buy_date = fields.Date(compute='_compute_profit', store=True)
    buy_fee = fields.Monetary(compute='_compute_profit', store=True)
    profit = fields.Monetary(string='Profit/Loss', compute='_compute_profit', store=True)

    @api.depends('sell_batch_id.usage')
    def _compute_simulated(self):
        for r in self: r.simulated = r.sell_batch_id.usage == 'realized'

    def _compute_profit(self):
        for record in self:
            sell_portion = (record.quantity / abs(record.sell_batch_id.quantity_adjusted))
            record.sell_date = record.sell_batch_id.time.date()
            record.sell_fee = record.sell_batch_id.fee * sell_portion
            record.sell_price = record.sell_batch_id.payment * sell_portion + record.sell_fee

            buy_portion = (record.quantity / abs(record.buy_batch_id.quantity_adjusted))
            record.buy_date = record.buy_batch_id.time.date()
            record.buy_fee = record.buy_batch_id.fee * buy_portion
            record.buy_price = record.buy_batch_id.payment * buy_portion - record.buy_fee

            record.profit = record.sell_price - record.sell_fee - record.buy_price - record.buy_fee


    _sql_constraints = [
        ('unique_realized', 'UNIQUE(sell_batch_id, buy_batch_id)', 'A realization for this aquisition/sell link already exists!'),
    ]
