# -*- coding: utf-8 -*-

import logging
import socket
import ssl
import json
from contextlib import contextmanager
from odoo import api, fields, models, Command, _
from ..electrum.bitcoin import address_to_scripthash
from odoo.exceptions import UserError, ValidationError
from btclib.script.script_pub_key import ScriptPubKey
from btclib.bip32 import derive

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

    first_key_id = fields.Many2one(
        comodel_name='bitcoin.key',
        compute='_compute_first_key_id',
    )

    script_type = fields.Selection(
        related='first_key_id.script_type',
        depends=['key_ids'],
    )

    def _compute_first_key_id(self):
        for wallet in self:
            wallet.first_key_id = wallet.key_ids[:1].key_id


    def _compute_multisig(self):
        for wallet in self:
            wallet.multisig = len(wallet.key_ids) > 1


    def refresh(self):
        self.filtered(lambda w: not w.address_ids).refresh_addresses()
        self.refresh_transactions()
        self.refresh_history()


    def refresh_addresses(self):
        address_map = {
            # Rare
            'p2pk': lambda pubkey: ScriptPubKey.p2pk(pubkey).address,

            # Legacy
            'p2pkh': lambda pubkey: ScriptPubKey.p2pkh(pubkey).address,
            'p2sh': lambda redeem_script: ScriptPubKey.p2sh(redeem_script).address,

            # Segwit
            'p2wpkh': lambda pubkey: ScriptPubKey.p2wpkh(pubkey).address,
            'p2wsh': lambda redeem_script: ScriptPubKey.p2wsh(redeem_script).address,
            'p2tr': lambda pubkey: ScriptPubKey.p2tr(pubkey).address,
        }

        sisig = {'p2wpkh', 'p2tr', 'p2pkh', 'p2pk'}
        musig = {'p2sh', 'p2wsh'}
        for wallet in self:
            existing = {(str(r.atype), str(r.index)): r for r in wallet.address_ids}
            st = wallet.first_key_id.script_type
            for atype in range(2):
                for index in range(wallet.address_amount):
                    subkey_path = (str(atype), str(index))
                    if len(wallet.key_ids) > 1 and len(wallet.key_ids) <= 15:
                        if st not in musig:
                            raise ValidationError(_("Multisig not supported for script type %s. Supported types %s.") % (st, musig))
                        keys = [derive(k.key_id.wif, subkey_path) for k in wallet.key_ids]
                        p2ms = ScriptPubKey.p2ms(
                            m=wallet.sigs_required,
                            keys=keys
                        )
                        addr_str = address_map[st](p2ms.script)
                    elif len(wallet.key_ids) == 1:
                        if st not in sisig:
                            raise ValidationError(_("Multisig not supported for script type %s. Supported types %s.") % (st, sisig))
                        addr_str = address_map[st](derive(wallet.first_key_id.wif, subkey_path))
                    else:
                        raise UserError(_("Wrong amount of keys: %s") % len(wallet.key_ids))


                    if subkey_path in existing:
                        if existing[subkey_path].address != addr_str:
                            existing[subkey_path].write({
                                'address': addr_str,
                                'scripthash_status': False,
                                'transaction_ids': [Command.clear()],
                            })
                    else:
                        existing[subkey_path] = self.env['bitcoin.wallet.address'].create({
                            'address': addr_str,
                            'index': index,
                            'atype': str(atype),
                            'wallet_id': wallet.id
                        })

    def _electrum_batch(self, send, host, port, method, params_list):
        requests = [
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": params,
            }
            for request_id, params in enumerate(params_list, 1)
        ]
        if not requests:
            return []

        _logger.info("%s batch(%s)", method, len(requests))
        responses = send(requests)
        if not isinstance(responses, list):
            raise UserError(_("%s:%s returned non-batch response for %s: %s") % (host, port, method, responses))
        if len(responses) != len(requests):
            raise UserError(_("%s:%s returned wrong response count for %s: %s") % (host, port, method, responses))

        result_by_id = {}
        for response in responses:
            if not isinstance(response, dict) or "id" not in response:
                raise UserError(_("%s:%s returned invalid response for %s: %s") % (host, port, method, response))
            if "error" in response and response["error"]:
                raise UserError(_("%s:%s returned RPC error for %s: %s") % (host, port, method, response["error"]))
            if "result" not in response:
                raise UserError(_("%s:%s response has no result for %s: %s") % (host, port, method, response))
            result_by_id[response["id"]] = response

        expected_ids = set(range(1, len(requests) + 1))
        if set(result_by_id) != expected_ids:
            raise UserError(_("%s:%s returned mismatched response ids for %s: %s") % (host, port, method, responses))
        return [result_by_id[request["id"]] for request in requests]

    def _electrum_server_version(self, send):
        response = send({
            "jsonrpc": "2.0",
            "method": "server.version",
            "params": ["", "1.4"],
            "id": 0,
        })
        if "result" in response:
            return response["result"]
        return response

    def _find_transactions_by_txid(self, txids):
        tx_by_hash = {}
        Tx = self.env['bitcoin.tx']
        for tx_hash in txids:
            _logger.info("TX search(%s)", tx_hash)
            tx = Tx.search([('txid', '=', tx_hash)])
            if not tx:
                raise UserError(_("Bitcoin TX '%s' not found") % tx_hash)
            tx_by_hash[tx_hash] = tx
        return tx_by_hash

    def refresh_transactions(self):
        get_param = self.env['ir.config_parameter'].sudo().get_param
        host = get_param('electrumx.host', '127.0.0.1')
        port = int(get_param('electrumx.port', '50001'))
        use_ssl = int(get_param('electrumx.use_ssl', '0'))

        with electumx_jsonrpc(host, port, use_ssl) as send:
            for wallet in self:
                per_type = {}
                for addr_record in wallet.address_ids:
                    per_type.setdefault(addr_record.atype, []).append(addr_record)

                for atype, addr_records in per_type.items():
                    subscribe_responses = wallet._electrum_batch(
                        send,
                        host,
                        port,
                        "blockchain.scripthash.subscribe",
                        [[addr_record.scripthash] for addr_record in addr_records],
                    )
                    empty = 0
                    changed = {}
                    for addr_record, response in zip(addr_records, subscribe_responses):
                        status = response["result"]
                        if status is None:
                            if addr_record.transaction_ids:
                                addr_record.transaction_ids = [Command.clear()]
                            if addr_record.scripthash_status:
                                addr_record.scripthash_status = False
                            empty += 1
                        else:
                            if not isinstance(status, str):
                                raise UserError(_("%s:%s returned invalid status for %s: %s") % (host, port, addr_record.scripthash, response))
                            empty = 0
                            if addr_record.scripthash_status != status:
                                changed[addr_record] = status

                        if empty >= wallet.gap_limit:
                            _logger.info("Stop checking after %s empty addresses of type %s.", empty, atype)
                            break
                    else:
                        if not empty:
                            raise UserError(_("Ran out of addresses! Please icrease address amount."))


                    history_responses = wallet._electrum_batch(
                        send,
                        host,
                        port,
                        "blockchain.scripthash.get_history",
                        [[addr_record.scripthash] for addr_record in changed],
                    )
                    history_by_addr = {}
                    tx_hashes = []
                    known_tx_hashes = set()
                    for addr_record, response in zip(changed, history_responses):
                        trans_list = response["result"]
                        if trans_list is None:
                            version = wallet._electrum_server_version(send)
                            raise UserError(_("%s:%s response has no transactions: %s. Version: %s") % (host, port, response, version))
                        if not isinstance(trans_list, list):
                            raise UserError(_("%s:%s returned invalid history for %s: %s") % (host, port, addr_record.scripthash, response))
                        _logger.info("%s has %s transactions", addr_record.address, len(trans_list))
                        history_by_addr[addr_record] = trans_list
                        for vals in trans_list:
                            tx_hash = vals['tx_hash']
                            if tx_hash not in known_tx_hashes:
                                known_tx_hashes.add(tx_hash)
                                tx_hashes.append(tx_hash)

                    tx_by_hash = wallet._find_transactions_by_txid(tx_hashes)
                    for addr_record, trans_list in history_by_addr.items():
                        tx_ids = []
                        for vals in trans_list:
                            tx = tx_by_hash[vals['tx_hash']]
                            if tx.id not in tx_ids:
                                tx_ids.append(tx.id)
                        addr_record.write({
                            'transaction_ids': [Command.set(tx_ids)],
                            'scripthash_status': changed[addr_record],
                        })

                _logger.info("Wallet %s done.", wallet.name)

    def refresh_history(self):
        for wallet in self:
            existing = {h.transaction_id: h for h in wallet.history_ids}
            addr_balance = {}
            for tx in wallet.address_ids.transaction_ids:
                amount = 0.0
                for addr in tx.wallet_address_ids.filtered(lambda a: a.wallet_id == wallet):
                    for vin in tx.vin_ids:
                        if addr.address == vin.spent_output_id.address:
                            amount -= vin.spent_output_id.value
                            addr_balance[addr] = addr_balance.get(addr, 0) - vin.spent_output_id.value
                    for vout in tx.vout_ids:
                        if addr.address == vout.address:
                            amount += vout.value
                            addr_balance[addr] = addr_balance.get(addr, 0) + vout.value

                vals = {
                    'amount': amount,
                    'date':  tx.blocktime or tx.block_id.time or fields.Datetime.now(),
                }

                History = self.env['bitcoin.wallet.history'].with_context(
                    default_wallet_id=wallet.id,
                    default_transaction_id=tx.id,
                )
                if tx in existing:
                    existing[tx].write(vals)
                else:
                    existing[tx] = History.create(vals)


            for addr, balance in addr_balance.items():
                addr.balance = balance

            wallet.balance = sum(wallet.mapped('history_ids.amount'))
            wallet.transactions = len(wallet.history_ids)





class BitcoinWalletKey(models.Model):
    _name = 'bitcoin.wallet.key'
    _description = 'Bitcoin Wallet Key'
    _order = 'sequence, id'
    _inherits = {'bitcoin.key': 'key_id'}


    key_id = fields.Many2one(
        comodel_name='bitcoin.key',
        required=True,
        ondelete='restrict',
    )

    wallet_id = fields.Many2one(
        comodel_name='bitcoin.wallet',
        required=True,
        ondelete='cascade',
    )

    sequence = fields.Integer()

    _wallet_key_uniq = models.Constraint('unique(wallet_id, key_id)', 'The wallet already has this key!')


class BitcoinWalletAddress(models.Model):
    _name = 'bitcoin.wallet.address'
    _description = 'Bitcoin Wallet Address'
    _inherit = ['mail.thread']
    _order = 'atype, index, id'
    _rec_name = 'address'

    address = fields.Char(
        required=True,
        readonly=True,
        tracking=True,
    )
    atype = fields.Selection(
        string="Type",
        selection=[
            ('0', 'Receiving'),
            ('1', 'Change'),
        ],
        required=True,
        readonly=True,
        tracking=True,
    )
    index = fields.Integer(
        readonly=True,
        required=True,
        tracking=True,
    )
    wallet_id = fields.Many2one(
        comodel_name='bitcoin.wallet',
        required=True,
        readonly=True,
        ondelete='cascade',
        tracking=True,
    )

    transaction_ids = fields.Many2many(
        comodel_name='bitcoin.tx',
        readonly=True,
    )

    balance = fields.Float(
        digits='Bitcoin Decimal',
        readonly=True,
    )

    scripthash = fields.Char(
        compute='_compute_scripthash',
        store=True,
        readonly=True,
        index=True,
    )

    scripthash_status = fields.Char(readonly=True)

    @api.depends('address')
    def _compute_scripthash(self):
        for record in self:
            if record.address:
                record.scripthash = address_to_scripthash(record.address)
            else:
                record.scripthash = False

    _wallet_address_uniq = models.Constraint('unique(wallet_id, address)', 'The wallet already has this address!')

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
        ondelete='cascade',
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
            if record.amount > 0:
                record.other_wallet_ids = record.transaction_id.vin_ids.mapped('wallet_ids')
            else:
                record.other_wallet_ids = record.transaction_id.vout_ids.mapped('wallet_ids')

            if len(record.transaction_id.vout_ids) > 1:
                record.other_wallet_ids -= record.wallet_id # remove change address wallet


    _wallet_transaction_uniq = models.Constraint('unique(wallet_id, transaction_id)', 'You should net out the balance change of one transaction instead of creating multiple lines per transaction!')
