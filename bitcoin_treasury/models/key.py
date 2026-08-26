# -*- coding: utf-8 -*-

from btclib.bip32 import BIP32KeyData, derive
from btclib.exceptions import BTClibValueError
from btclib.network import xpubversions_from_network
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

    wif = fields.Char(
        string="Extended Public Key",
        help="Mainnet extended public key used exclusively for watch-only address derivation.",
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

    multisig = fields.Boolean(
        help="Specify whether this extended public key is used for multisignature address derivation.",
        tracking=True,
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
    script_type = fields.Selection(
        string="Script Type",
        selection=[
            # Rare
            ('p2pk', 'Pay To Public Key'),
            ('p2ms', 'Pay To Multisig'), # "Bare multisig"

            # LEGACY
            ('p2pkh', 'Pay to Public Key Hash (m/44)'),
            ('p2sh', 'Pay to Script Hash (m/45)'),
            ('p2sh_p2wpkh', 'Pay To Witness Public Key Hash Wrapped In P2SH (m/49)'),
            ('p2sh_p2wsh', 'Pay To Witness Script Hash Wrapped In P2SH (m/48h/0h/0h/1h)'),

            # Segwit
            ('p2wpkh', 'Pay To Witness Public Key Hash (m/84)'),
            ('p2wsh', 'Pay To Witness Script Hash (m/48h/0h/0h/2h)'),
            ('p2tr', 'Pay To Taproot (m/86)'),
        ],
        compute='_compute_script_type',
        help=(
            "BIP44 specifies derivation paths m / purpose' / coin_type' / account' / change / address_index."
        ),
        tracking=True,
        store=True,
        readonly=False,
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

    real_parent_fingerprint = fields.Char(
        string="Master Key Fingerprint",
        help="Eight-character fingerprint of the master key, used in the descriptor key origin.",
        tracking=True,
    )
    real_derivation_path = fields.Char(
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

    @api.depends('witness_type', 'multisig')
    def _compute_script_type(self):
        for rec in self:
            rec.script_type = self._script_type_default(rec.witness_type, rec.multisig)

    def _script_type_default(self, witness_type, multisig):
        if witness_type == 'legacy':
            return 'p2sh' if multisig else 'p2pkh'
        if witness_type == 'segwit':
            return 'p2wsh' if multisig else 'p2wpkh'
        if witness_type == 'p2sh-segwit':
            return 'p2sh'
        if witness_type == 'taproot':
            return 'p2tr'
        raise ValidationError(
            _("Wallet and extended public key type combination not supported: %s / %s")
            % (witness_type, multisig)
        )

    @api.depends('witness_type')
    def _compute_encoding(self):
        for rec in self:
            rec.encoding = self._witness_encoding_map[rec.witness_type]

    def _decode_extended_public_key(self, value):
        try:
            key_data = BIP32KeyData.b58decode(value)
        except BTClibValueError as error:
            raise ValidationError(_("A valid mainnet extended public key is required.")) from error
        if key_data.is_private or key_data.version not in xpubversions_from_network('mainnet'):
            raise ValidationError(_("A valid mainnet extended public key is required."))
        return key_data

    def _derive_public_key(self, derivation_path):
        self.ensure_one()
        return derive(self.wif, derivation_path)

    def _key_origin_error(self):
        self.ensure_one()
        fingerprint = self.real_parent_fingerprint
        if self.real_derivation_path and not fingerprint:
            return _("Add the master key fingerprint or remove the derivation path.")
        if fingerprint and (
            len(fingerprint) != 8
            or any(character not in '0123456789abcdefABCDEF' for character in fingerprint)
        ):
            return _("The master key fingerprint must contain exactly eight hexadecimal characters.")

        path = self.real_derivation_path
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
        key_data = self._decode_extended_public_key(self.wif)
        xpub = BIP32KeyData(
            version=xpubversions_from_network('mainnet')[0],
            depth=key_data.depth,
            parent_fingerprint=key_data.parent_fingerprint,
            index=key_data.index,
            chain_code=key_data.chain_code,
            key=key_data.key,
        ).b58encode()
        origin = ''
        if self.real_parent_fingerprint:
            path = self.real_derivation_path or ''
            if path == 'm':
                path = ''
            elif path.startswith('m/'):
                path = path[2:]
            path = path.replace("'", 'h')
            origin = '[%s%s]' % (
                self.real_parent_fingerprint.lower(),
                '/%s' % path if path else '',
            )
        return '%s%s/<0;1>/*' % (origin, xpub)

    @api.constrains('real_parent_fingerprint', 'real_derivation_path')
    def _check_key_origin(self):
        for key in self:
            error = key._key_origin_error()
            if error:
                raise ValidationError(error)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._decode_extended_public_key(vals['wif'])
        return super().create(vals_list)

    def write(self, vals):
        if 'wif' in vals:
            self._decode_extended_public_key(vals['wif'])
        return super().write(vals)
