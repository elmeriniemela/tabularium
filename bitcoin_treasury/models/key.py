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
        help="Canonical BIP32 extended public key with version prefix 0x0488B21E. Used for watch-only derivation "
        "across any script type (Legacy, SegWit, Taproot) and in modern output script descriptors.",
        required=True,
        tracking=True,
        inverse='_inverse_xpub',
    )
    zpub = fields.Char(
        string="zpub",
        help="SLIP-0132 extended public key with version prefix 0x04B24746 for BIP84 single-key Native SegWit "
        "(P2WPKH, bc1q... addresses). Used by single-signature wallets (e.g. Electrum, Sparrow). The version "
        "prefix is the only difference to xpub.",
        tracking=True,
        inverse='_inverse_zpub',
    )
    Zpub = fields.Char(
        string="Zpub",
        help="SLIP-0132 extended public key with version prefix 0x02AA7ED3 for BIP48 multisig Native SegWit "
        "(P2WSH, bc1q... addresses). Used by multisignature coordinators and hardware wallets (e.g. Coldcard, Sparrow). "
        "The version prefix is the only difference to xpub.",
        tracking=True,
        inverse='_inverse_Zpub',
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
        required=True,
        tracking=True,
    )
    derivation = fields.Char(
        string="Derivation Path",
        help="Path from the master key to this extended public key, used in the descriptor key origin.",
        required=True,
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

    def _inverse_xpub(self):
        for key in self:
            target_zpub = self._to_zpub(key.xpub) if key.xpub else False
            if key.zpub != target_zpub:
                key.zpub = target_zpub
            target_Zpub = self._to_Zpub(key.xpub) if key.xpub else False
            if key.Zpub != target_Zpub:
                key.Zpub = target_Zpub

    def _inverse_zpub(self):
        for key in self:
            target_xpub = self._to_xpub(key.zpub) if key.zpub else False
            if key.xpub != target_xpub:
                key.xpub = target_xpub

    def _inverse_Zpub(self):
        for key in self:
            target_xpub = self._to_xpub(key.Zpub) if key.Zpub else False
            if key.xpub != target_xpub:
                key.xpub = target_xpub

    def _to_Zpub(self, key_str):
        if not key_str:
            return False
        return self._decode_extended_public_key(key_str).to_Zpub()

    def _to_zpub(self, key_str):
        if not key_str:
            return False
        return self._decode_extended_public_key(key_str).to_zpub()

    def _to_xpub(self, key_str):
        if not key_str:
            return False
        return self._decode_extended_public_key(key_str).to_xpub()

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
        fingerprint = self.master_fingerprint or ''
        if len(fingerprint) != 8 or any(character not in '0123456789abcdefABCDEF' for character in fingerprint):
            return _("The master key fingerprint must contain exactly eight hexadecimal characters.")

        path = self.derivation or ''
        if path != 'm':
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
        return '%s%s/<0;1>/*' % (origin, key_data.to_xpub())

    @api.constrains('master_fingerprint', 'derivation')
    def _check_key_origin(self):
        for key in self:
            error = key._key_origin_error()
            if error:
                raise ValidationError(error)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            source = vals.get('xpub') or vals.get('zpub') or vals.get('Zpub')
            if source:
                if not vals.get('xpub'):
                    vals['xpub'] = self._to_xpub(source)
                if not vals.get('zpub'):
                    vals['zpub'] = self._to_zpub(source)
                if not vals.get('Zpub'):
                    vals['Zpub'] = self._to_Zpub(source)
            if vals.get('master_fingerprint'):
                vals['master_fingerprint'] = vals['master_fingerprint'].lower()
            if vals.get('derivation'):
                vals['derivation'] = vals['derivation'].lower().replace("'", 'h')
            for field in ('xpub', 'zpub', 'Zpub'):
                if vals.get(field):
                    self._decode_extended_public_key(vals[field])
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('master_fingerprint'):
            vals['master_fingerprint'] = vals['master_fingerprint'].lower()
        if vals.get('derivation'):
            vals['derivation'] = vals['derivation'].lower().replace("'", 'h')
        for field in ('xpub', 'zpub', 'Zpub'):
            if vals.get(field):
                self._decode_extended_public_key(vals[field])
        return super().write(vals)
