# -*- coding: utf-8 -*-
from odoo import api, models, fields, _


class CashflowEntry(models.Model):
    _name = 'cashflow.entry'
    _description = 'Cash Flow Entry'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc'

    name = fields.Char(required=True)
    date = fields.Date(required=True, default=fields.Date.today)
    amount = fields.Monetary(required=True, currency_field='company_currency_id')

    company_id = fields.Many2one(comodel_name='res.company', required=True, default=lambda self: self.env.company)
    category_id = fields.Many2one(comodel_name='cashflow.category', required=True)

    active = fields.Boolean(related='account_id.active')
    account_id = fields.Many2one(
        comodel_name='cashflow.account',
        required=True,
        ondelete='restrict',
    )
    company_currency_id = fields.Many2one(related='company_id.currency_id', string="Company Currency", readonly=True)

    parser_id = fields.Many2one(comodel_name='cashflow.parser', required=True)
    raw = fields.Text(readonly=True)
    identifier = fields.Char(readonly=True)
    attachment_id = fields.Many2one(comodel_name='ir.attachment', ondelete='cascade', required=True, domain="[('res_model', '=', 'cashflow.parser'), ('res_id', '=', parser_id)]")
    entry_type = fields.Selection(
        selection=[
            ('deposit', 'Deposit'),
            ('withdrawal', 'Withdrawal'),
        ],
        compute='_compute_entry_type',
        store=True,
    )

    _zero_amount = models.Constraint('CHECK(amount != 0)', 'Amount can not be zero!')

    @api.depends('amount')
    def _compute_entry_type(self):
        for record in self:
            record.entry_type = 'deposit' if record.amount > 0 else 'withdrawal'