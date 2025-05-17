# -*- coding: utf-8 -*-

import logging
import hashlib
from bitcoinlib.scripts import Script
from bitcoinlib.keys import Address, deserialize_address
import socket
import ssl
import json
from contextlib import contextmanager
from odoo import api, exceptions, fields, models, Command, _
from ..electrum.bitcoin import address_to_scripthash
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

@contextmanager
def electumx_jsonrpc(host, port, use_ssl):
    if use_ssl:
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        sock = context.wrap_socket(socket.socket(socket.AF_INET, socket.SOCK_STREAM))
    else:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    sock.settimeout(10)
    try:
        sock.connect((host, port))
    except Exception as error:
        raise UserError(("Unable to connect to host '%s:%s': %s") % (host, port, str(error)))


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

        resp = b''.join(responselist)
        assert resp, f"Empty response: {host}:{port} ({use_ssl=})"
        return json.loads(resp)

    try:
        yield send
    finally:
        sock.close()



class BitcoinWallet(models.Model):
    _name = 'bitcoin.wallet'
    _inherit = ['mail.thread', 'mail.activity.mixin']
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

    sigs_required = fields.Integer(default=1)

    multisig = fields.Boolean(compute='_compute_multisig')

    balance = fields.Float(
        digits='Bitcoin Decimal',
        readonly=True,
    )

    transactions = fields.Integer(
        readonly=True,
    )

    address_amount = fields.Integer(default=100, tracking=True)
    gap_limit = fields.Integer(default=5, tracking=True)

    def _compute_multisig(self):
        for wallet in self:
            wallet.multisig = len(wallet.key_ids) > 1


    def refresh(self):
        self.filtered(lambda w: not w.address_ids).refresh_addresses()
        self.refresh_transactions()
        self.refresh_history()


    def refresh_addresses(self):
        for wallet in self:
            existing = {('M', str(r.atype), str(r.index)): r for r in wallet.address_ids}
            master_keys = [k.key_id.hdkey for k in wallet.key_ids]
            for atype in range(2):
                for index in range(wallet.address_amount):
                    subkey_path = ('M', str(atype), str(index))
                    subkeys = [k.subkey_for_path(subkey_path) for k in master_keys]
                    subkeys.sort(key=lambda k: k.public_byte)
                    first_key = wallet.key_ids[:1].key_id
                    if len(subkeys) > 1 and len(subkeys) <= 15:
                        # MULTISIG
                        redeemscript = Script(
                            script_types=['multisig'],
                            keys=subkeys,
                            sigs_required=wallet.sigs_required,
                        )
                        addr = Address(
                            redeemscript.serialize(),
                            encoding=first_key.encoding,
                            script_type=first_key.script_type,
                        )
                        addr_str = addr.address
                    elif len(subkeys) == 1:
                        # SINGLE-SIG
                        addr_str = subkeys[0].address(
                            script_type=first_key.script_type,
                            encoding=first_key.encoding,
                        )
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

    def refresh_transactions(self):
        get_param = self.env['ir.config_parameter'].sudo().get_param
        host = get_param('electrumx.host', '127.0.0.1')
        port = int(get_param('electrumx.port', '50001'))
        use_ssl = int(get_param('electrumx.use_ssl', '0'))

        with electumx_jsonrpc(host, port, use_ssl) as send:
            for wallet in self:
                per_type = {}
                addr_to_rec = {}
                for addr_record in wallet.address_ids:
                    per_type.setdefault(addr_record.atype, []).append(addr_record.address)
                    addr_to_rec[addr_record.address] = addr_record

                for atype, addr_list in per_type.items():
                    empty = 0
                    for address in addr_list:
                        sh = address_to_scripthash(address)
                        _logger.info("get_history(%s)", sh)
                        tx_json = send({
                            "method": "blockchain.scripthash.get_history",
                            "params": {
                                "scripthash": sh,
                            },
                            "id": 0
                        })

                        trans_list = tx_json['result']
                        _logger.info("%s has %s transactions", address, len(trans_list))
                        if tx_json['result']:
                            empty = 0
                            for vals in tx_json['result']:
                                tx_hash = vals['tx_hash']
                                _logger.info("TX search(%s)", tx_hash)
                                tx = self.env['bitcoin.tx'].search([('txid', '=', tx_hash)])
                                if not tx:
                                    raise UserError(_("Bitcoin TX '%s' not found") % tx_hash)
                                addr_to_rec[address].transaction_ids |= tx
                        else:
                            empty +=1

                        if empty >= wallet.gap_limit:
                            _logger.info("Stop checking after %s empty addresses of type %s.", empty, atype)
                            break


                _logger.info("Wallet %s done.", wallet.name)

    def refresh_history(self):
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
                    'date': tx.block_id.time or fields.Datetime.now(),
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

    wallet_history_ids = fields.One2many(
        comodel_name='bitcoin.wallet.history',
        inverse_name='transaction_id',
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

    other_wallet_ids = fields.Many2many(
        comodel_name='bitcoin.wallet',
        compute='_compute_other_wallet_ids',
    )

    def _compute_other_wallet_ids(self):
        for record in self:
            record.other_wallet_ids = (record.transaction_id.wallet_history_ids - record).mapped('wallet_id')



    _sql_constraints = [
        ('wallet_transaction_uniq', 'unique(wallet_id, transaction_id)', 'You should net out the balance change of one transaction instead of creating multiple lines per transaction!'),
    ]

