# -*- coding: utf-8 -*-

from bitwalkit import EncodingError, ExtendedKey
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class BitcoinExtendedPublicKey(models.Model):
    _name = 'bitcoin.key'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Bitcoin Extended Public Key'
    _order = 'sequence, id'

    sequence = fields.Integer()
    name = fields.Char(tracking=True)
    active = fields.Boolean(default=True, tracking=True)
    compromised = fields.Boolean(tracking=True)

    xpub = fields.Char(
        string="xpub",
        help="Mainnet extended public key used for watch-only address derivation.",
        required=True,
        tracking=True,
    )

    wallet_ids = fields.One2many(
        string="Watch-only Wallets",
        comodel_name='bitcoin.wallet.key',
        inverse_name='key_id',
        readonly=True,
        context={'active_test': False},
    )

    witness_type = fields.Selection(
        selection=[
            ('taproot', 'Taproot'),
            ('segwit', 'Segwit'),
            ('p2sh-segwit', 'P2SH Segwit'),
            ('legacy', 'Legacy'),
        ],
        default='segwit',
        tracking=True,
        required=True,
    )
    encoding = fields.Selection(
        selection=[
            ('bech32', 'bech32'),
            ('base58', 'base58'),
        ],
        default='bech32',
        compute='_compute_encoding',
        tracking=True,
        required=True,
        store=True,
    )

    master_fingerprint = fields.Char(
        string="Master Key Fingerprint",
        help="Eight-character fingerprint of the master key, used in the descriptor key origin.",
        tracking=True,
    )
    derivation = fields.Char(
        string="Derivation Path",
        help="Path from the master key to this extended public key, used in the descriptor key origin.",
        tracking=True,
    )

    _witness_encoding_map = {
        'segwit': 'bech32',
        'taproot': 'bech32',
        'p2sh-segwit': 'base58',
        'legacy': 'base58',
    }

    @api.depends('witness_type')
    def _compute_encoding(self):
        for rec in self:
            rec.encoding = self._witness_encoding_map[rec.witness_type]

    def _decode_extended_public_key(self, value):
        try:
            key_data = ExtendedKey.parse(value)
        except EncodingError as error:
            raise ValidationError(_("A valid mainnet extended public key is required.")) from error
        if key_data.network != 'mainnet':
            raise ValidationError(_("A valid mainnet extended public key is required."))
        return key_data

    def _key_origin_error(self):
        self.ensure_one()
        fingerprint = self.master_fingerprint
        if self.derivation and not fingerprint:
            return _("Add the master key fingerprint or remove the derivation path.")
        if fingerprint and (
            len(fingerprint) != 8
            or any(character not in '0123456789abcdefABCDEF' for character in fingerprint)
        ):
            return _("The master key fingerprint must contain exactly eight hexadecimal characters.")

        path = self.derivation
        if path and path != 'm':
            if path.startswith('m/'):
                path = path[2:]
            for step in path.split('/'):
                number = step[:-1] if step.endswith(("'", 'h')) else step
                if not number.isdigit() or int(number) >= 2**31:
                    return _("Enter a valid BIP32 derivation path.")
        return False

    def _descriptor_key(self):
        self.ensure_one()
        key_data = self._decode_extended_public_key(self.xpub)
        xpub = key_data.to_xpub()
        origin = ''
        if self.master_fingerprint:
            path = self.derivation or ''
            if path == 'm':
                path = ''
            elif path.startswith('m/'):
                path = path[2:]
            path = path.replace("'", 'h')
            origin = '[%s%s]' % (
                self.master_fingerprint.lower(),
                '/%s' % path if path else '',
            )
        return '%s%s/<0;1>/*' % (origin, xpub)

    @api.constrains('master_fingerprint', 'derivation')
    def _check_key_origin(self):
        for key in self:
            error = key._key_origin_error()
            if error:
                raise ValidationError(error)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('master_fingerprint'):
                vals['master_fingerprint'] = vals['master_fingerprint'].lower()
            if vals.get('derivation'):
                vals['derivation'] = vals['derivation'].lower().replace("'", 'h')
            if 'xpub' in vals:
                self._decode_extended_public_key(vals['xpub'])
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('master_fingerprint'):
            vals['master_fingerprint'] = vals['master_fingerprint'].lower()
        if vals.get('derivation'):
            vals['derivation'] = vals['derivation'].lower().replace("'", 'h')
        if 'xpub' in vals:
            self._decode_extended_public_key(vals['xpub'])
        return super().write(vals)
