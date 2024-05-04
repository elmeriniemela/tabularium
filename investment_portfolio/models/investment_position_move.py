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
    )

    time = fields.Datetime(required=True, default=fields.Datetime.now, tracking=True)

    position_id = fields.Many2one(
        comodel_name='investment.position',
        required=True,
        ondelete='cascade',
        index=True,
        tracking=True,
    )

    asset_id = fields.Many2one(related='position_id.asset_id')
    currency_id = fields.Many2one(related='position_id.currency_id')
    company_currency_id = fields.Many2one(related='position_id.company_currency_id')
    company_id = fields.Many2one(related='position_id.company_id')

    transaction_ids = fields.One2many(
        comodel_name='investment.position.transaction',
        inverse_name='move_id',
    )


