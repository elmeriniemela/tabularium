# -*- coding: utf-8 -*-

from odoo import api, exceptions, fields, models, Command, _


class Position(models.Model):
    _inherit = 'investment.position'

    wallet_ids = fields.One2many(
        comodel_name='bitcoin.wallet',
        inverse_name='position_id',
        readonly=True,
        context={'active_test': False},
    )

    wallet_count = fields.Integer(compute='_compute_wallet_count')

    def _compute_wallet_count(self):
        for record in self.sudo():
            record.wallet_count = len(record.wallet_ids)

    def fetch_bitcoin_transactions(self):
        self.sudo().mapped('wallet_ids').refresh()



