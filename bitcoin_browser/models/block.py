# -*- coding: utf-8 -*-

import datetime
import tinyrpc
import logging
from dateutil.relativedelta import relativedelta

from odoo import api, exceptions, fields, models, Command, _


_logger = logging.getLogger(__name__)


class BitcoinBlock(models.Model):
    _name = 'bitcoin.block'
    _description = 'Bitcoin Block'
    _rec_name = 'hash'
    _order = 'height desc'

    hash = fields.Char(required=True, help="The hash of the block header.")
    confirmations = fields.Integer(help="The number of confirmations, or -1 if the block is not on the main chain")
    height = fields.Integer(help="The block height or index.")
    version = fields.Integer(help="A version number to track software/protocol upgrades.")

    merkleroot = fields.Char(help="Copies of each transaction are hashed, and the hashes are then paired, hashed, paired again, and hashed again until a single hash remains, the merkle root of a merkle tree.")
    time = fields.Datetime(help="The timestamp is chosen by the miners, and has some restrictions on it such as it can't be too far in the future/past (no more than 2 hours into the future), but it is not strictly increasing.")
    mediantime = fields.Datetime(help="Mediantime is the median time of the past 11 block timestamps, and a block must have a timestamp greater than that median time, so the mediantime always increases.")

    nonce = fields.BigInteger(help="A counter used for the proof-of-work algorithm.")

    bits = fields.Char(help="bits refers to nBits, which encodes the target difficulty for the block. The target threshold is a 256-bit unsigned integer which a header hash must be equal to or below in order for that header to be a valid part of the block chain. However, the header field nBits provides only 32 bits of space, so the target number uses a less precise format called “compact” which works like a base-256 version of scientific notation. https://developer.bitcoin.org/reference/block_chain.html?highlight=nbits#target-nbits")

    difficulty = fields.Float(help="Difficulty is basically a different representation of the target to make it easier for normal humans to understand it. Difficulty represents how difficult the current target makes it to find a block, relative to how difficult it would be at the highest possible target (highest target=lowest difficulty). The current difficulty of 6,695,826 means that at a given hash rate, it will, on average, take ~6.6 million times as long to find a valid block as it would at a difficulty of 1, or alternatively, it will take, again on average, ~6.6 million times as many hashes to find a valid block.")
    chainwork = fields.Char(help="The total amount of work in the chain. For example, converting 0000000000000000000000000000000000000000000086859f7a841475b236fd to decimal, you get 635262017308958427068157, or 635262 exahashes. At june 2014 hash rates (100 petahash/s), it would require only 73 days to perform that many hashes, while in reality it took over 5 years. The hash rate has been going up so fast however that the impact of more than a few months ago is negligible.")
    n_tx = fields.Integer()
    computed_n_tx = fields.Integer(compute='_compute_computed_n_tx', store=True)
    all_tx_fetched = fields.Boolean(compute='_compute_computed_n_tx', store=True)

    previousblockhash = fields.Char(help="Each block also stores the hash of the previous block's header, chaining the blocks together. This ensures a transaction cannot be modified without modifying the block that records it and all following blocks.")

    size = fields.Integer(help="Refers to the size of the block, which is 80 bytes for the header + sum(tx_sizes). This includes the segwit data and is meant to match the actual, on disk size of the block.")
    strippedsize = fields.Integer(help="The block size excluding witness data.")
    weight = fields.Integer(help="Block weight is defined as Base size * 3 + Total size. Base size is the block size in bytes with the original transaction serialization without any witness-related data, as seen by a non-upgraded node. Total size is the block size in bytes with transactions serialized as described in BIP144, including base data and witness data. The new rule is block weight less or equal to 4,000,000.")

    tx_ids = fields.One2many(
        comodel_name='bitcoin.tx',
        inverse_name='block_id',
        readonly=True,
        help="Bitcoin wallet software gives the impression that satoshis are sent from and to wallets, but bitcoins really move from transaction to transaction. Each transaction spends the satoshis previously received in one or more earlier transactions, so the input of one transaction is the output of a previous transaction. A single transaction can create multiple outputs, as would be the case when sending to multiple addresses, but each output of a particular transaction can only be used as an input once in the block chain. Any subsequent reference is a forbidden double spend—an attempt to spend the same satoshis twice."
    )

    _sql_constraints = [
        ('uniq', 'unique(hash)', 'The block hash should be unique!')
    ]


    @api.depends('tx_ids')
    def _compute_computed_n_tx(self):
        res = self.env['bitcoin.tx'].read_group(
            domain=[('block_id', 'in', self.ids)],
            fields=['block_id'],
            groupby=['block_id'],
            lazy=False,
        )
        counts = {(r['block_id'][0]): r['__count'] for r in res}
        for record in self:
            record.computed_n_tx = counts.get(record.id, 0)
            record.all_tx_fetched = counts.get(record.id) == record.n_tx

    @api.model
    def cron_fetch(self):
        delta = int(self.env['ir.config_parameter'].sudo().get_param('bitoind.history.hours', '1'))
        mintime = fields.Datetime.now() - relativedelta(hours=delta)
        proxy = self.env['ir.config_parameter'].bitcoind_proxy()
        getblockchaininfo = proxy.getblockchaininfo()
        current_hash = getblockchaininfo['bestblockhash']
        current_block = self.search([('hash', '=', current_hash)])
        confirmations = 1
        while mintime <= current_block.mediantime:
            self.env.cr.commit()
            confirmations +=1
            _logger.info("Update block %s.", current_block.height)
            current_block = self.search([('hash', '=', current_block.previousblockhash)])
            if not current_block.mediantime:
                current_block.refresh()
            current_block.confirmations = confirmations


    @api.model
    def getblock(self, hash, tx=False):
        verbosity = 2 if tx else 1
        proxy = self.env['ir.config_parameter'].bitcoind_proxy()

        _logger.info(f"proxy.getblock({hash}, {verbosity})")
        try:
            getblock = proxy.getblock(hash, verbosity)
        except tinyrpc.protocols.jsonrpc.JSONRPCError as error:
            raise exceptions.UserError(error.args[0])
        _logger.info("Done.")

        vals = {
            'hash': hash,
            'confirmations': getblock['confirmations'],
            'height': getblock['height'],
            'version': getblock['version'],
            'merkleroot': getblock['merkleroot'],
            'time': datetime.datetime.utcfromtimestamp(getblock['time']),
            'mediantime': datetime.datetime.utcfromtimestamp(getblock['mediantime']),
            'nonce': getblock['nonce'],
            'bits': getblock['bits'],
            'difficulty': getblock['difficulty'],
            'chainwork': getblock['chainwork'],
            'n_tx': getblock['nTx'],
            'previousblockhash': getblock['previousblockhash'] if getblock['height'] != 0 else False,
            'size': getblock['size'],
            'strippedsize': getblock['strippedsize'],
            'weight': getblock['weight'],
        }

        if tx:
            tx_ids = []
            for rawtx in getblock['tx']:
                txvals = {
                    'in_active_chain': rawtx.get('in_active_chain'),
                    'txid': rawtx['txid'],
                    'hash': rawtx['hash'],
                    'version': rawtx['version'],
                    'size': rawtx['size'],
                    'vsize': rawtx['vsize'],
                    'weight': rawtx['weight'],
                    'locktime': rawtx['locktime'],
                    'fee': rawtx.get('fee', 0.0),
                    'vin_ids': [
                        Command.create({
                            'sequence': vin['sequence'],
                            'vout_tx_id': vin.get('txid', False),
                            'vout': vin.get('vout', False),
                            'coinbase': vin.get('coinbase', False),
                        }) for vin in rawtx['vin']
                    ],
                    'vout_ids': [
                        Command.create({
                            'n': vout['n'],
                            'value': vout['value'],
                            'address': vout['scriptPubKey'].get('address', False),
                            'asm': vout['scriptPubKey']['asm'],
                            'type': vout['scriptPubKey']['type'],
                        }) for vout in rawtx['vout']
                    ]
                }
                tx_ids.append(Command.create(txvals))

            vals['tx_ids'] = tx_ids

        return vals

    def refresh(self):
        for record in self:
            record = record.with_context(default_block_id=record.id)
            _logger.info("Update block at height %s.", record.height)
            vals = record.getblock(record.hash, tx=True)
            record.write(vals)
            record.env.cr.commit()

    @api.model
    def _search(self, domains, offset=0, limit=None, order=None, count=False, access_rights_uid=None):
        res = super()._search(domains, offset, limit, order, count=count, access_rights_uid=access_rights_uid)
        found = res if count else len(res)
        if not self.env.context.get('disable_auto_populate') and not found and len(domains) == 1:
            field, operator, value = domains[0]
            if field == 'hash' and operator == '=':
                auto = self.create({'hash': value})
                auto.with_context(force_tx=True).refresh()
                res = 1 if count else auto.ids
        return res

    @api.model_create_multi
    def create(self, vals_list):
        filtered_vals_list = []
        existing = self.browse()
        for vals in vals_list:
            found = self.with_context(disable_auto_populate=True).search([('hash', '=', vals['hash'])])
            if found:
                found.write(vals)
                existing += found
            else:
                filtered_vals_list.append(vals)
        return super().create(filtered_vals_list) + existing


