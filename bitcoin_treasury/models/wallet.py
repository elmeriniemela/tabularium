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
        with electumx_jsonrpc('127.0.0.1', 50001) as send:
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
                    _logger.info('%s: %s', addr.address, tx_json)



class BitcoinWallet(models.Model):
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


    _sql_constraints = [
        ('wallet_address_uniq', 'unique(wallet_id, address)', 'The wallet already has this address!'),
    ]


