# -*- coding: utf-8 -*-
from odoo import api, models, fields, _

class CashflowEntry(models.Model):
    _name = 'cashflow.plan'
    _description = 'Cash Flow Entry'
    _order = 'sequence, id'

    def _default_date(self):
        today = fields.Date.today()
        if today.day < 15:
            return today.replace(day=15)
        else:
            return fields.Date.add(today, months=1).replace(day=15)


    sequence = fields.Integer(default=10_000)
    name = fields.Char(required=True)
    date = fields.Date(required=True, default=_default_date)
    amount = fields.Monetary(required=True, currency_field='company_currency_id')
    company_id = fields.Many2one(comodel_name='res.company', required=True, default=lambda self: self.env.company)
    company_currency_id = fields.Many2one(related='company_id.currency_id', string="Company Currency", readonly=True)

    balance = fields.Monetary(compute='_compute_balance', currency_field='company_currency_id')

    _sql_constraints = [
        ('zero_amount', 'CHECK(amount != 0)', 'Amount can not be zero!'),
    ]

    @api.onchange('sequence')
    def _compute_balance(self):
        balance = 0
        for record in self.search([]):
            balance += record.amount
            record.balance = balance
