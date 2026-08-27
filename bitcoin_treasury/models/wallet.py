# -*- coding: utf-8 -*-

import calendar
import logging

from bitwalkit import (
    BitwalkitError,
    ChainQuery,
    address_from_pubkey,
    address_from_script,
    address_to_scripthash,
    descriptor_checksum,
    p2ms_script,
)
from odoo import api, fields, models, Command, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)



class BitcoinWallet(models.Model):
    _name = 'bitcoin.wallet'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Bitcoin Watch-only Wallet'
    _order = 'sequence, id'

    sequence = fields.Integer()
    name = fields.Char()
    active = fields.Boolean(default=True, tracking=True)

    history_ids = fields.One2many(
        comodel_name='bitcoin.wallet.history',
        inverse_name='wallet_id',
    )

    key_ids = fields.One2many(
        comodel_name='bitcoin.wallet.key',
        inverse_name='wallet_id',
        context={'active_test': False},
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
        context={'active_test': False},
    )

    script_type = fields.Selection(
        related='first_key_id.script_type',
        depends=['key_ids'],
    )

    descriptor = fields.Char(
        compute='_compute_descriptor',
        help="Bitcoin Core descriptor, or instructions for completing the wallet configuration.",
    )
    birth_timestamp = fields.Char(
        string="Birth Timestamp",
        compute='_compute_descriptor_timestamp',
        help="Unix timestamp for Bitcoin Core descriptor imports, based on the earliest wallet transaction or wallet creation time.",
    )

    def _compute_first_key_id(self):
        for wallet in self:
            wallet.first_key_id = wallet.key_ids[:1].key_id


    def _compute_multisig(self):
        for wallet in self:
            wallet.multisig = len(wallet.key_ids) > 1

    @api.depends('history_ids.date', 'create_date')
    def _compute_descriptor_timestamp(self):
        for wallet in self:
            timestamp = min(wallet.history_ids.mapped('date'), default=wallet.create_date)
            wallet.birth_timestamp = str(calendar.timegm(timestamp.utctimetuple())) if timestamp else False

    @api.depends(
        'sigs_required',
        'key_ids',
        'key_ids.sequence',
        'key_ids.key_id.wif',
        'key_ids.key_id.script_type',
        'key_ids.key_id.real_parent_fingerprint',
        'key_ids.key_id.real_derivation_path',
    )
    def _compute_descriptor(self):
        for wallet in self:
            key_count = len(wallet.key_ids)
            origin_error = False
            for key in wallet.key_ids.key_id:
                origin_error = key._key_origin_error()
                if origin_error:
                    break
            if origin_error:
                wallet.descriptor = origin_error
            elif not key_count:
                wallet.descriptor = _("Add an extended public key to compute the descriptor.")
            elif key_count == 1 and wallet.script_type != 'p2wpkh':
                wallet.descriptor = _("Use a native SegWit single-signature extended public key.")
            elif key_count > 15:
                wallet.descriptor = _("Use no more than 15 extended public keys.")
            elif key_count > 1 and any(key.script_type != 'p2wsh' for key in wallet.key_ids.key_id):
                wallet.descriptor = _("Use native SegWit multisig for every extended public key.")
            elif key_count > 1 and not 0 < wallet.sigs_required <= key_count:
                wallet.descriptor = _("Set Required Signatures between 1 and the number of extended public keys.")
            elif key_count == 1:
                descriptor = 'wpkh(%s)' % wallet.first_key_id._descriptor_key()
                wallet.descriptor = '%s#%s' % (descriptor, descriptor_checksum(descriptor))
            else:
                keys = ','.join(wallet_key.key_id._descriptor_key() for wallet_key in wallet.key_ids)
                descriptor = 'wsh(sortedmulti(%s,%s))' % (wallet.sigs_required, keys)
                wallet.descriptor = '%s#%s' % (descriptor, descriptor_checksum(descriptor))


    def refresh(self):
        self.filtered(lambda w: not w.address_ids).refresh_addresses()
        self.refresh_transactions()
        self.refresh_history()


    def refresh_addresses(self):
        address_map = {
            # Legacy
            'p2pkh': 'p2pkh',
            'p2sh': 'p2sh',

            # Wrapped segwit.
            'p2sh_p2wpkh': 'p2sh-p2wpkh',
            'p2sh_p2wsh': 'p2sh-p2wsh',

            # Segwit / taproo
            'p2tr': 'p2tr',
            'p2wpkh': 'p2wpkh',
            'p2wsh': 'p2wsh',
        }
        sisig = {'p2wpkh', 'p2sh_p2wpkh', 'p2tr', 'p2pkh'}
        musig = {'p2sh', 'p2wsh', 'p2sh_p2wsh'}
        for wallet in self:
            existing = {(str(r.atype), str(r.index)): r for r in wallet.address_ids}
            st = wallet.first_key_id.script_type
            for atype in range(2):
                for index in range(wallet.address_amount):
                    subkey_path = (str(atype), str(index))
                    if len(wallet.key_ids) > 1 and len(wallet.key_ids) <= 15:
                        if st not in musig:
                            raise ValidationError(_("Multisig not supported for script type %s. Supported types %s.") % (st, musig))
                        keys = [k.key_id._derive_public_key(subkey_path) for k in wallet.key_ids]
                        keys.sort()
                        addr_str = address_from_script(
                            p2ms_script(wallet.sigs_required, keys), address_map[st]
                        )
                    elif len(wallet.key_ids) == 1:
                        if st not in sisig:
                            raise ValidationError(_("Multisig not supported for script type %s. Supported types %s.") % (st, sisig))
                        addr_str = address_from_pubkey(
                            wallet.first_key_id._derive_public_key(subkey_path),
                            address_map[st],
                        )
                    else:
                        raise UserError(_("Wrong amount of extended public keys: %s") % len(wallet.key_ids))


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
        use_ssl = bool(int(get_param('electrumx.use_ssl', '0')))
        chain = ChainQuery(host, port, use_ssl)

        try:
            for wallet in self:
                per_type = {}
                for addr_record in wallet.address_ids:
                    per_type.setdefault(addr_record.atype, []).append(addr_record)

                for atype, addr_records in per_type.items():
                    _logger.info("Subscribe batch(%s)", len(addr_records))
                    statuses = chain.get_statuses([record.address for record in addr_records])
                    empty = 0
                    changed = {}
                    for addr_record in addr_records:
                        status = statuses[addr_record.address]
                        if status is None:
                            if addr_record.transaction_ids:
                                addr_record.transaction_ids = [Command.clear()]
                            if addr_record.scripthash_status:
                                addr_record.scripthash_status = False
                            empty += 1
                        else:
                            empty = 0
                            if addr_record.scripthash_status != status:
                                changed[addr_record] = status

                        if empty >= wallet.gap_limit:
                            _logger.info("Stop checking after %s empty addresses of type %s.", empty, atype)
                            break
                    else:
                        if not empty:
                            raise UserError(_("Ran out of addresses! Please icrease address amount."))


                    _logger.info("History batch(%s)", len(changed))
                    histories = chain.get_history_many([record.address for record in changed])
                    history_by_addr = {}
                    tx_hashes = []
                    known_tx_hashes = set()
                    for addr_record in changed:
                        trans_list = histories[addr_record.address]
                        _logger.info("%s has %s transactions", addr_record.address, len(trans_list))
                        history_by_addr[addr_record] = trans_list
                        for entry in trans_list:
                            tx_hash = entry.txid
                            if tx_hash not in known_tx_hashes:
                                known_tx_hashes.add(tx_hash)
                                tx_hashes.append(tx_hash)

                    tx_by_hash = wallet._find_transactions_by_txid(tx_hashes)
                    for addr_record, trans_list in history_by_addr.items():
                        tx_ids = []
                        for entry in trans_list:
                            tx = tx_by_hash[entry.txid]
                            if tx.id not in tx_ids:
                                tx_ids.append(tx.id)
                        addr_record.write({
                            'transaction_ids': [Command.set(tx_ids)],
                            'scripthash_status': changed[addr_record],
                        })

                _logger.info("Wallet %s done.", wallet.name)
        except BitwalkitError as error:
            raise UserError(str(error)) from error

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
    _description = 'Bitcoin Wallet Extended Public Key'
    _order = 'sequence, id'
    _inherits = {'bitcoin.key': 'key_id'}

    name = fields.Char(related='wallet_id.name')

    key_id = fields.Many2one(
        comodel_name='bitcoin.key',
        required=True,
        ondelete='restrict',
        context={'active_test': True},
    )

    wallet_id = fields.Many2one(
        comodel_name='bitcoin.wallet',
        required=True,
        ondelete='cascade',
    )

    sequence = fields.Integer()

    _wallet_key_uniq = models.Constraint(
        'unique(wallet_id, key_id)',
        'The wallet already has this extended public key!',
    )


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
            record.scripthash = record._address_to_scripthash(record.address) if record.address else False

    @staticmethod
    def _address_to_scripthash(address):
        return address_to_scripthash(address)

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
        context={'active_test': False},
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
