# -*- coding: utf-8 -*-

import logging
import hashlib
from bitcoinlib.scripts import Script
from bitcoinlib.keys import Address, deserialize_address
import socket
import json
from contextlib import contextmanager
from odoo import api, exceptions, fields, models, Command, _
from ..electrum.bitcoin import address_to_scripthash

_logger = logging.getLogger(__name__)

@contextmanager
def electumx_jsonrpc(host, port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(10)
    sock.connect((host, port))
    def send(content):
        sock.sendall(json.dumps(content).encode('utf-8')+b'\n')
        responselist = []
        buffer = 1024
        while True:
            data = sock.recv(buffer)
            if not data:
                break
            responselist.append(data)
            if len(data) < buffer:
                break
        return json.loads(b''.join(responselist))

    try:
        yield send
    finally:
        sock.close()



class BitcoinWallet(models.Model):
    _name = 'bitcoin.wallet'
    _description = 'Bitcoin Wallet'
    _order = 'sequence, id'

    sequence = fields.Integer()
    name = fields.Char()

    history_ids = fields.One2many(
        comodel_name='bitcoin.wallet.history',
        inverse_name='wallet_id',
    )

    key_ids = fields.One2many(
        comodel_name='bitcoin.wallet.key',
        inverse_name='wallet_id',
    )

    address_ids = fields.One2many(
        comodel_name='bitcoin.wallet.address',
        inverse_name='wallet_id',
        readonly=True,
    )

    sigs_required = fields.Integer()

    multisig = fields.Boolean(compute='_compute_multisig')

    balance = fields.Float(
        digits='Bitcoin Decimal',
        readonly=True,
    )

    transactions = fields.Integer(
        readonly=True,
    )

    def _compute_multisig(self):
        for wallet in self:
            wallet.multisig = len(wallet.key_ids) > 1

    def update_addresses(self):
        for wallet in self:
            existing = {('M', str(r.atype), str(r.index)): r for r in wallet.address_ids}
            master_keys = [k.key_id.hdkey for k in wallet.key_ids]
            for atype in range(2):
                for index in range(100):
                    subkey_path = ('M', str(atype), str(index))
                    subkeys = [k.subkey_for_path(subkey_path) for k in master_keys]
                    subkeys.sort(key=lambda k: k.public_byte)
                    if len(subkeys) > 1 and len(subkeys) <= 15:
                        # MULTISIG
                        redeemscript = Script(
                            script_types=['multisig'],
                            keys=subkeys,
                            sigs_required=wallet.sigs_required,
                        )
                        addr = Address(redeemscript.serialize(), encoding=wallet.key_ids[:1].key_id.encoding, script_type='p2wsh')
                        addr_str = addr.address
                    elif len(subkeys) == 1:
                        # SINGLE-SIG
                        addr_str = subkeys[0].address()
                    else:
                        raise exceptions.UserError(_("Wrong amount of keys: %s") % len(subkeys))


                    if subkey_path in existing:
                        existing[subkey_path].address = addr_str
                    else:
                        existing[subkey_path] = self.env['bitcoin.wallet.address'].create({
                            'address': addr_str,
                            'index': index,
                            'atype': str(atype),
                            'wallet_id': wallet.id
                        })

    def update_transactions(self):
        get_param = self.env['ir.config_parameter'].sudo().get_param
        host = get_param('electrumx.host', '127.0.0.1')
        port = int(get_param('electrumx.port', '50001'))

        with electumx_jsonrpc(host, port) as send:
            for wallet in self:
                for addr in wallet.address_ids:
                    sh = address_to_scripthash(addr.address)
                    tx_json = send({
                        "method": "blockchain.scripthash.get_history",
                        "params": {
                            "scripthash": sh,
                        },
                        "id": 0
                    })
                    for vals in tx_json['result']:
                        addr.transaction_ids |= self.env['bitcoin.tx'].search([('txid', '=', vals['tx_hash'])])

    def update_history(self):
        for wallet in self:
            existing = {h.transaction_id: h for h in wallet.history_ids}
            for tx in wallet.address_ids.transaction_ids:
                amount = 0.0
                for addr in tx.wallet_address_ids.filtered(lambda a: a.wallet_id == wallet):
                    for vin in tx.vin_ids:
                        if addr.address == vin.spent_output_id.address:
                            amount -= vin.spent_output_id.value
                    for vout in tx.vout_ids:
                        if addr.address == vout.address:
                            amount += vout.value

                vals = {
                    'amount': amount,
                    'date': tx.block_id.time,
                }

                History = self.env['bitcoin.wallet.history'].with_context(
                    default_wallet_id=wallet.id,
                    default_transaction_id=tx.id,
                )
                if tx in existing:
                    existing[tx].write(vals)
                else:
                    existing[tx] = History.create(vals)

            wallet.balance = sum(wallet.mapped('history_ids.amount'))
            wallet.transactions = len(wallet.history_ids)





class BitcoinWalletKey(models.Model):
    _name = 'bitcoin.wallet.key'
    _description = 'Bitcoin Wallet Key'
    _order = 'sequence, id'

    key_id = fields.Many2one(
        comodel_name='bitcoin.key',
        required=True,
    )

    wallet_id = fields.Many2one(
        comodel_name='bitcoin.wallet',
        required=True,
    )

    sequence = fields.Integer()

    _sql_constraints = [
        ('wallet_key_uniq', 'unique(wallet_id, key_id)', 'The wallet already has this key!'),
    ]


class BitcoinWalletAddress(models.Model):
    _name = 'bitcoin.wallet.address'
    _description = 'Bitcoin Wallet Address'
    _order = 'atype, index, id'
    _rec_name = 'address'

    address = fields.Char(
        required=True,
        readonly=True,
    )
    atype = fields.Selection(
        string="Type",
        selection=[
            ('0', 'Receiving'),
            ('1', 'Change'),
        ],
        required=True,
        readonly=True,
    )
    index = fields.Integer(
        readonly=True,
        required=True,
    )
    wallet_id = fields.Many2one(
        comodel_name='bitcoin.wallet',
        required=True,
        readonly=True,
    )

    transaction_ids = fields.Many2many(
        comodel_name='bitcoin.tx',
        readonly=True,
    )


    _sql_constraints = [
        ('wallet_address_uniq', 'unique(wallet_id, address)', 'The wallet already has this address!'),
    ]

class BitcoinTx(models.Model):
    _inherit = 'bitcoin.tx'

    wallet_address_ids = fields.Many2many( # Inverse lookup.
        comodel_name='bitcoin.wallet.address',
        readonly=True,
    )


class BitcoinWalletHistory(models.Model):
    _name = 'bitcoin.wallet.history'
    _description = 'Bitcoin Wallet History'
    _order = 'date desc, id desc'

    wallet_id = fields.Many2one(
        comodel_name='bitcoin.wallet',
        required=True,
        readonly=True,
    )

    date = fields.Datetime(
        readonly=True,
        required=True,
    )

    name = fields.Char(string="Description")


    amount = fields.Float(
        digits='Bitcoin Decimal',
        readonly=True,
        required=True,
    )

    transaction_id = fields.Many2one(
        comodel_name='bitcoin.tx',
        ondelete='restrict',
        required=True,
        readonly=True,
    )

    _sql_constraints = [
        ('wallet_transaction_uniq', 'unique(wallet_id, transaction_id)', 'You should net out the balance change of one transaction instead of creating multiple lines per transaction!'),
    ]

