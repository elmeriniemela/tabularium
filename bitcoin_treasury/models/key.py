# -*- coding: utf-8 -*-

import logging

from odoo import api, exceptions, fields, models, Command, _
from odoo.exceptions import ValidationError
from btclib.to_pub_key import fingerprint

def script_type_default(witness_type=None, multisig=False, locking_script=False):
    """
    Determine default script type for provided witness type and key type combination used in this library.

    >>> script_type_default('segwit', locking_script=True)
    'p2wpkh'

    :param witness_type: Witness type used: standard, p2sh-segwit or segwit
    :type witness_type: str
    :param multisig: Multi-signature key or not, default is False
    :type multisig: bool
    :param locking_script: Limit search to locking_script. Specify False for locking scripts and True for unlocking scripts
    :type locking_script: bool

    :return str: Default script type
    """

    if witness_type == 'legacy' and not multisig:
        return 'p2pkh' if locking_script else 'sig_pubkey'
    elif witness_type == 'legacy' and multisig:
        return 'p2sh' if locking_script else 'p2sh_multisig'
    elif witness_type == 'segwit' and not multisig:
        return 'p2wpkh' if locking_script else 'sig_pubkey'
    elif witness_type == 'segwit' and multisig:
        return 'p2wsh' if locking_script else 'p2sh_multisig'
    elif witness_type == 'p2sh-segwit' and not multisig:
        return 'p2sh' if locking_script else 'p2sh_p2wpkh'
    elif witness_type == 'p2sh-segwit' and multisig:
        return 'p2sh' if locking_script else 'p2sh_p2wsh'
    elif witness_type == 'taproot':
        return 'p2tr'
    else:
        raise ValidationError("Wallet and key type combination not supported: %s / %s" % (witness_type, multisig))


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
        string="Wallets",
        comodel_name='bitcoin.wallet.key',
        inverse_name='key_id',
        readonly=True,
    )

    multisig = fields.Boolean(
        help="Specify if key is part of multisig wallet, used when creating key representations such as WIF and addreses",
        tracking=True,
    )
    fingerprint = fields.Char(
        compute='_compute_fingerprint',
        store=True,
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

    real_parent_fingerprint = fields.Char(tracking=True)
    real_derivation_path = fields.Char(tracking=True)


    _script_encoding_map = {
        'p2pk': 'base58',
        'p2pkh': 'base58',
        'p2ms': 'base58',
        'p2sh': 'base58',
        'p2sh_p2wpkh': 'base58',
        'p2sh_p2wsh': 'base58',
        'p2wpkh': 'bech32',
        'p2wsh': 'bech32',
        'p2tr': 'bech32',
    }
    _witness_encoding_map = {
        'segwit': 'bech32',
        'taproot': 'bech32',
        'p2sh-segwit': 'base58',
        'legacy': 'base58',
    }



    @api.depends('witness_type', 'multisig')
    def _compute_script_type(self):
        for rec in self:
            rec.script_type = script_type_default(rec.witness_type, rec.multisig, locking_script=True)


    @api.depends('witness_type')
    def _compute_encoding(self):
        for rec in self:
            rec.encoding = self._witness_encoding_map[rec.witness_type]


    @api.depends('wif')
    def _compute_fingerprint(self):
        for record in self:
            if record.wif:
                record.fingerprint = fingerprint(record.wif, "mainnet").hex()
            else:
                record.fingerprint = False

