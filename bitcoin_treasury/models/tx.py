# -*- coding: utf-8 -*-

import logging

from odoo import api, exceptions, fields, models, Command, _
from odoo.exceptions import ValidationError


class BitcoinOut(models.Model):
    _inherit = 'bitcoin.tx.out'

    wallet_ids = fields.Many2many(
        comodel_name='bitcoin.wallet',
        compute='_compute_wallet_ids',
    )

    @api.depends('address')
    def _compute_wallet_ids(self):
        for record in self:
            record.wallet_ids = record.env['bitcoin.wallet.address'].search([
                ('address', '=', record.address),
            ]).mapped('wallet_id')

class BitcoinIn(models.Model):
    _inherit = 'bitcoin.tx.in'

    wallet_ids = fields.Many2many(
        comodel_name='bitcoin.wallet',
        compute='_compute_wallet_ids',
    )

    @api.depends('spent_output_id')
    def _compute_wallet_ids(self):
        for record in self:
            record.wallet_ids = record.spent_output_id.wallet_ids
