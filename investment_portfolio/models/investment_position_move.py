# -*- coding: utf-8 -*-

from odoo import api, models, fields, _
import logging

_logger = logging.getLogger(__name__)

class InvestmentPositionMove(models.Model):
    _name = 'investment.position.move'
    _description = 'Position Move'
    _inherit = ['mail.thread']
    _order = 'id desc'

    name = fields.Char(
        required=True,
        default='/',
    )

    company_id = fields.Many2one(
        comodel_name='res.company',
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )

    company_currency_id = fields.Many2one(related='company_id.currency_id')

    cash_flow = fields.Monetary(
        compute='_compute_cash_flow',
        help="Cash flow related to this transaction. Positive sum means that money went in to move, negative sum means that money came out of move.",
        currency_field='company_currency_id'
    )

    time = fields.Datetime(required=True, default=fields.Datetime.now, tracking=True)

    transaction_ids = fields.One2many(
        comodel_name='investment.position.transaction',
        inverse_name='move_id',
        domain="[('company_id', '=', company_id)]",
    )

    _sql_constraints = [
        ('unique_name', 'unique(name, company_id)', 'A move with this name already exists!'),
    ]


    @api.model_create_multi
    def create(self, vals_list):
        number = 0
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                time = vals.get('time') or fields.Datetime.now()
                if not number:
                    prev = self.search([
                        ('name', '=like', f'MOVE/{time.year}/%'),
                        ('company_id', '=', vals['company_id']),
                    ], order='name desc', limit=1)
                    if prev.name:
                        number = int(prev.name.split('/')[-1])
                number += 1
                vals['name'] = f'MOVE/{time.year}/{str(number).zfill(5)}'

        return super().create(vals_list)

    @api.depends('transaction_ids.cash_flow')
    def _compute_cash_flow(self):
        for move in self:
            move.cash_flow = sum(move.transaction_ids.mapped('cash_flow'))




