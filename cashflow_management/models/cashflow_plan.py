# -*- coding: utf-8 -*-
from odoo import api, models, fields, _

class CashflowEntry(models.Model):
    _name = 'cashflow.plan'
    _description = 'Cash Plan'
    name = fields.Char(required=True)
    company_id = fields.Many2one(comodel_name='res.company', required=True, default=lambda self: self.env.company)
    company_currency_id = fields.Many2one(related='company_id.currency_id', string="Company Currency", readonly=True)

    line_ids = fields.One2many(
        comodel_name='cashflow.plan.line',
        inverse_name='plan_id',
        string='Lines',
        copy=True,
    )


class CashflowEntry(models.Model):
    _name = 'cashflow.plan.line'
    _description = 'Cash Plan Line'
    _order = 'sequence, id'

    def _default_date(self):
        today = fields.Date.today()
        if today.day < 15:
            return today.replace(day=15)
        else:
            return fields.Date.add(today, months=1).replace(day=15)


    plan_id = fields.Many2one(
        comodel_name='cashflow.plan',
        required=True,
        readonly=True,
        index=True,
        ondelete='cascade',
    )
    sequence = fields.Integer(default=10_000)
    name = fields.Char(required=True)
    date = fields.Date(required=True, default=_default_date)
    amount = fields.Monetary(required=True, currency_field='company_currency_id')
    company_id = fields.Many2one(related='plan_id.company_id')
    company_currency_id = fields.Many2one(related='plan_id.company_id.currency_id')

    balance = fields.Monetary(compute='_compute_balance', currency_field='company_currency_id')

    _zero_amount = models.Constraint('CHECK(amount != 0)', 'Amount can not be zero!')

    def _compute_balance(self):
        for plan in self.plan_id:
            balance = 0
            for line in plan.line_ids:
                balance += line.amount
                line.balance = balance

