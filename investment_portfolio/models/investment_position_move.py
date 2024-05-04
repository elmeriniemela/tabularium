# -*- coding: utf-8 -*-

from odoo import api, models, fields, _
from odoo.tools import float_is_zero
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
        company = self.env.company
        consume = self.env['investment.position'].search([('asset_id.ticker', '=', 'CONSUME'), ('company_id', '=', company.id)])
        consume.ensure_one()

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

        moves = super().create(vals_list)
        for move in moves:
            cash_flow = sum(move.transaction_ids.mapped('cash_flow'))
            if not float_is_zero(cash_flow, precision_digits=consume.currency_id.decimal_places):
                self.env['investment.position.transaction'].create({
                    'position_id': consume.id,
                    'move_id': move.id,
                    'time': move.transaction_ids[:1].time,
                    'quantity': cash_flow * -1,
                    'payment': cash_flow,
                    'exchange_rate': 1,
                })

        return moves





