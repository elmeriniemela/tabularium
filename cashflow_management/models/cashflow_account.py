# -*- coding: utf-8 -*-

from odoo import api, models, fields, _


class CashflowCategory(models.Model):
    _name = 'cashflow.account'
    _description = 'Cash Flow Account'
    _order = 'sequence, id'

    name = fields.Char(required=True)
    sequence = fields.Integer(string='Sequence')

    parser_ids = fields.Many2many(comodel_name='cashflow.parser')

    active = fields.Boolean(default=True)

    entry_ids = fields.One2many(
        comodel_name='cashflow.entry',
        inverse_name='account_id',
        readonly=True,
    )

    _sql_constraints = [
        ('unique_name', 'unique(name)', 'This account already exists!'),
    ]

