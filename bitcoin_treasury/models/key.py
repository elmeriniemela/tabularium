# -*- coding: utf-8 -*-

import logging

from odoo import api, exceptions, fields, models, Command, _

from bitcoinlib.keys import HDKey

_logger = logging.getLogger(__name__)


class BitcoinKey(models.Model):
    _name = 'bitcoin.key'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Bitcoin Key'
    _order = 'sequence, id'

    sequence = fields.Integer()
    name = fields.Char(tracking=True)

    wif = fields.Char(required=True, tracking=True)

    wallet_ids = fields.One2many(
        comodel_name='bitcoin.wallet.key',
        inverse_name='key_id',
        readonly=True,
    )

    secret = fields.Boolean(compute='_compute_info', store=True)
    compressed = fields.Boolean(compute='_compute_info', store=True)
    multisig = fields.Boolean(compute='_compute_info', store=True)
    depth = fields.Integer(compute='_compute_info', store=True)
    parent_fingerprint = fields.Char(compute='_compute_info', store=True)
    key_type = fields.Char(compute='_compute_info', store=True)
    witness_type = fields.Char(compute='_compute_info', store=True)
    script_type = fields.Char(compute='_compute_info', store=True)
    address = fields.Char(compute='_compute_info', store=True)
    encoding = fields.Char(compute='_compute_info', store=True)

    real_parent_fingerprint = fields.Char(tracking=True)
    real_derivation_path = fields.Char(tracking=True)


    @property
    def hdkey(self):
        self.ensure_one()
        return HDKey(import_key=self.wif)

    @api.depends('wif')
    def _compute_info(self):
        for record in self:
            key = record.hdkey
            record.secret = key.secret
            record.compressed = key.compressed
            record.multisig = key.multisig
            record.depth = key.depth
            record.parent_fingerprint = key.parent_fingerprint.hex()
            record.key_type = key.key_type
            record.witness_type = key.witness_type
            record.script_type = key.script_type
            record.address = key.address()
            record.encoding = key.encoding

