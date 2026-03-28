# -*- coding: utf-8 -*-

from odoo import api, models, fields, _
from odoo.tools import float_compare
from odoo.tools.misc import formatLang

class InvestmentAssetRealized(models.Model):
    _name = 'investment.asset.realized'
    _description = 'Asset Realized'
    _order = 'realized_date asc, id asc'

    position_id = fields.Many2one(
        comodel_name='investment.position',
        required=True,
        ondelete='cascade',
        index=True,
    )

    company_currency_id = fields.Many2one(related='position_id.company_currency_id')
    currency_id = fields.Many2one(related='position_id.currency_id')
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

    sell_price = fields.Float(compute='_compute_profit', store=True, digits=[2,2])
    sell_payment = fields.Float(compute='_compute_profit', store=True, aggregator=None, digits=[2,2])
    sell_payment_currency = fields.Monetary(compute='_compute_profit', store=True, aggregator=None, currency_field='currency_id')
    sell_date = fields.Date(compute='_compute_profit', store=True)
    sell_fee = fields.Float(compute='_compute_profit', store=True, digits=[2,2])

    buy_price = fields.Float(compute='_compute_profit', store=True, digits=[2,2])
    buy_payment = fields.Float(compute='_compute_profit', store=True, aggregator=None, digits=[2,2])
    buy_payment_currency = fields.Monetary(compute='_compute_profit', store=True, aggregator=None, currency_field='currency_id')
    buy_date = fields.Date(compute='_compute_profit', store=True)
    buy_fee = fields.Float(compute='_compute_profit', store=True, digits=[2,2])
    realized_date = fields.Date(compute='_compute_profit', store=True)

    profit = fields.Float(string='Profit/Loss', compute='_compute_profit', store=True, digits=[2,2])
    is_profit = fields.Boolean(compute='_compute_profit', store=True)

    @api.depends('sell_batch_id.usage', 'buy_batch_id.usage')
    def _compute_simulated(self):
        for r in self: r.simulated = any(u == 'realized' for u in [r.sell_batch_id.usage, r.buy_batch_id.usage])

    def _compute_profit(self):
        for record in self:
            sell_portion = (record.quantity / abs(record.sell_batch_id.quantity_adjusted))
            sell_time = fields.Datetime.context_timestamp(
                record.with_context(tz=record.company_id.partner_id.tz),
                record.sell_batch_id.time,
            )
            record.sell_date = sell_time.date()
            sell_fee_currency = record.sell_batch_id.fee * sell_portion
            record.sell_fee = record.currency_id._convert(
                from_amount=sell_fee_currency,
                to_currency=record.company_currency_id,
                company=record.company_id,
                date=record.sell_batch_id.time,
            )
            record.sell_price = record.sell_batch_id.payment * sell_portion + record.sell_fee # TODO: should we minus the fee?
            record.sell_payment = record.sell_batch_id.payment * sell_portion
            record.sell_payment_currency = record.sell_batch_id.payment_currency * sell_portion

            buy_portion = (record.quantity / abs(record.buy_batch_id.quantity_adjusted))
            buy_time = fields.Datetime.context_timestamp(
                record.with_context(tz=record.company_id.partner_id.tz),
                record.buy_batch_id.time,
            )
            record.buy_date = buy_time.date()
            buy_fee_currency = record.buy_batch_id.fee * buy_portion
            record.buy_fee = record.currency_id._convert(
                from_amount=buy_fee_currency,
                to_currency=record.company_currency_id,
                company=record.company_id,
                date=record.buy_batch_id.time,
            )
            record.buy_price = record.buy_batch_id.payment * buy_portion - record.buy_fee
            record.buy_payment = record.buy_batch_id.payment * buy_portion
            record.buy_payment_currency = record.buy_batch_id.payment_currency * buy_portion

            record.profit = record.sell_price - record.sell_fee - record.buy_price - record.buy_fee
            record.realized_date = max([record.buy_date, record.sell_date])
            record.is_profit = float_compare(record.profit, 0, precision_digits=2) > 0

    def _get_report_totals(self):
        return {
            'profit': formatLang(self.env, sum(self.mapped('profit')), digits=2),
            'sell_price': formatLang(self.env, sum(self.mapped('sell_price')), digits=2),
            'sell_fee': formatLang(self.env, sum(self.mapped('sell_fee')), digits=2),
            'buy_price': formatLang(self.env, sum(self.mapped('buy_price')), digits=2),
            'buy_fee': formatLang(self.env, sum(self.mapped('buy_fee')), digits=2),
        }

    _sql_constraints = [
        ('unique_realized', 'UNIQUE(sell_batch_id, buy_batch_id)', 'A realization for this aquisition/sell link already exists!'),
    ]
