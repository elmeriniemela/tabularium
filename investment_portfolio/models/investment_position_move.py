# -*- coding: utf-8 -*-

from odoo import api, models, fields, _
from odoo.fields import Domain
import logging

_logger = logging.getLogger(__name__)

class InvestmentPositionMove(models.Model):
    _name = 'investment.position.move'
    _description = 'Position Move'
    _inherit = ['mail.thread']
    _order = 'time desc, id desc'

    name = fields.Char(
        required=True,
        default='/',
        tracking=True,
    )

    company_id = fields.Many2one(
        comodel_name='res.company',
        required=True,
        default=lambda self: self.env.company,
        index=True,
        tracking=True,
    )

    company_currency_id = fields.Many2one(related='company_id.currency_id')

    cash_flow = fields.Monetary(
        compute='_compute_cash_flow',
        help="Net cash flow of this move. Positive sum means that money went in to move, negative sum means that money came out of move.",
        currency_field='company_currency_id'
    )

    profit = fields.Monetary(compute='_compute_profit', currency_field='company_currency_id')

    time = fields.Datetime(required=True, default=fields.Datetime.now, tracking=True)

    transaction_ids = fields.One2many(
        comodel_name='investment.position.transaction',
        inverse_name='move_id',
        domain="[('company_id', '=', company_id)]",
    )

    position_ids = fields.Many2many(
        comodel_name='investment.position',
        string="Positions",
        compute='_compute_position_ids',
        search='_search_position_ids',
    )

    portfolio_ids = fields.Many2many(
        comodel_name='investment.portfolio',
        string="Portfolios",
        compute='_compute_portfolio_ids',
        search='_search_portfolio_ids',
    )

    note_id = fields.Many2one(
        string="Note ID",
        comodel_name='investment.position.note',
        ondelete='restrict',
    )
    note = fields.Html(
        string="Note",
        related='note_id.content',
        readonly=False,
        tracking=False,
    )

    _unique_name = models.Constraint('unique(name, company_id)', 'A move with this name already exists!')

    def _compute_portfolio_ids(self):
        for record in self:
            record.portfolio_ids = record.transaction_ids.mapped('portfolio_id')

    def _search_portfolio_ids(self, operator, value):
        if isinstance(value, bool):
            # portfolios is set
            # portfolios is not set
            return [('transaction_ids', operator, value)]

        domain = Domain('transaction_ids.portfolio_id', operator, value)
        if operator in Domain.NEGATIVE_OPERATORS:
            # Normal negative term operators do not work intuitively through One2many lists.
            # We need to negate outside of the leaf using '!', to have behaviour which makes sense to a user.
            # portfolios does not contain X
            # portfolios is not equal to X
            domain = ~Domain('transaction_ids.portfolio_id', Domain.NEGATIVE_OPERATORS[operator], value)

        _logger.debug(domain)
        return domain

    def _compute_position_ids(self):
        for record in self:
            record.position_ids = record.transaction_ids.mapped('position_id')

    def _search_position_ids(self, operator, value):
        if isinstance(value, bool):
            # Positions is set
            # Positions is not set
            return [('transaction_ids', operator, value)]

        domain = Domain('transaction_ids.position_id', operator, value)
        if operator in Domain.NEGATIVE_OPERATORS:
            # Normal negative term operators do not work intuitively through One2many lists.
            # We need to negate outside of the leaf using '!', to have behaviour which makes sense to a user.
            # Positions does not contain X
            # Positions is not equal to X
            domain = ~Domain('transaction_ids.position_id', Domain.NEGATIVE_OPERATORS[operator], value)

        _logger.debug(domain)
        return domain

    @api.model_create_multi
    def create(self, vals_list):
        number = 0
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                time = vals.get('time') or fields.Datetime.now()
                if isinstance(time, str):
                    time = fields.Datetime.from_string(time)

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


    @api.depends('transaction_ids')
    def _compute_profit(self):
        for move in self:
            tx = move.transaction_ids
            tx._compute_profit() # for some reason, we need to call it here when zeroing transaction values from move form.
            move.profit = sum(tx.mapped('profit'))

