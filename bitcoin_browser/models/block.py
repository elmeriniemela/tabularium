# -*- coding: utf-8 -*-

import datetime
import tinyrpc

from odoo import api, exceptions, fields, models, Command, _

class BitcoinBlock(models.Model):
    _name = 'bitcoin.block'
    _description = 'Bitcoin Block'
    _rec_name = 'hash'

    hash = fields.Char(required=True, help="The hash of the block header.")
    confirmations = fields.Integer(help="The number of confirmations, or -1 if the block is not on the main chain")
    height = fields.Integer(help="The block height or index.")

    merkleroot = fields.Char(help="Copies of each transaction are hashed, and the hashes are then paired, hashed, paired again, and hashed again until a single hash remains, the merkle root of a merkle tree.")
    time = fields.Datetime(help="The timestamp is chosen by the miners, and has some restrictions on it such as it can't be too far in the future/past (no more than 2 hours into the future), but it is not strictly increasing.")
    mediantime = fields.Datetime(help="Mediantime is the median time of the past 11 block timestamps, and a block must have a timestamp greater than that median time, so the mediantime always increases.")
    difficulty = fields.Float(help="Difficulty is basically a different representation of the target to make it easier for normal humans to understand it. Difficulty represents how difficult the current target makes it to find a block, relative to how difficult it would be at the highest possible target (highest target=lowest difficulty). The current difficulty of 6,695,826 means that at a given hash rate, it will, on average, take ~6.6 million times as long to find a valid block as it would at a difficulty of 1, or alternatively, it will take, again on average, ~6.6 million times as many hashes to find a valid block.")
    chainwork = fields.Char(help="The total amount of work in the chain. For example, converting 0000000000000000000000000000000000000000000086859f7a841475b236fd to decimal, you get 635262017308958427068157, or 635262 exahashes. At june 2014 hash rates (100 petahash/s), it would require only 73 days to perform that many hashes, while in reality it took over 5 years. The hash rate has been going up so fast however that the impact of more than a few months ago is negligible.")
    n_tx = fields.Integer()
    previousblockhash = fields.Char(help="Each block also stores the hash of the previous block's header, chaining the blocks together. This ensures a transaction cannot be modified without modifying the block that records it and all following blocks.")


    tx_ids = fields.One2many(
        comodel_name='bitcoin.tx',
        inverse_name='block_id',
        readonly=True,
        help="Bitcoin wallet software gives the impression that satoshis are sent from and to wallets, but bitcoins really move from transaction to transaction. Each transaction spends the satoshis previously received in one or more earlier transactions, so the input of one transaction is the output of a previous transaction. A single transaction can create multiple outputs, as would be the case when sending to multiple addresses, but each output of a particular transaction can only be used as an input once in the block chain. Any subsequent reference is a forbidden double spend—an attempt to spend the same satoshis twice."
    )

    _sql_constraints = [
        ('uniq', 'unique(hash)', 'The block hash should be unique!')
    ]

    def unlink(self):
        self.mapped('tx_ids.vin_ids.vout_tx_id').unlink() # Preceeding empty transactions (only txid), that were created on the fly based on 'vin'.
        return super().unlink()

    @api.model
    def getblock(self, hash, tx=False):
        verbosity = 2 if tx else 1
        proxy = self.env['ir.config_parameter'].bitcoind_proxy()

        try:
            getblock = proxy.getblock(hash, verbosity)
        except tinyrpc.protocols.jsonrpc.JSONRPCError as error:
            raise exceptions.UserError(error.args[0])

        vals = {
            'hash': hash,
            'confirmations': getblock['confirmations'],
            'height': getblock['height'],
            'merkleroot': getblock['merkleroot'],
            'time': datetime.datetime.utcfromtimestamp(getblock['time']),
            'mediantime': datetime.datetime.utcfromtimestamp(getblock['mediantime']),
            'difficulty': getblock['difficulty'],
            'chainwork': getblock['chainwork'],
            'previousblockhash': getblock['previousblockhash'],
            'n_tx': getblock['nTx'],
        }

        if tx:
            tx_ids = []
            for rawtx in getblock['tx']:
                txvals = self.tx_ids.rawtx_to_vals(rawtx)
                tx_ids.append(Command.create(txvals))

            vals['tx_ids'] = tx_ids

        return vals

    def refresh(self):
        for record in self:
            tx = record.n_tx != len(record.tx_ids)
            record = record.with_context(default_block_id=record.id)
            record.write(record.getblock(record.hash, tx=tx))

    @api.model
    def _search(self, domains, offset=0, limit=None, order=None, count=False, access_rights_uid=None):
        res = super()._search(domains, offset, limit, order, count=count, access_rights_uid=access_rights_uid)
        found = res if count else len(res)
        if not self.env.context.get('disable_auto_populate') and not found and len(domains) == 1:
            field, operator, value = domains[0]
            if field == 'hash' and operator == '=':
                block = self.getblock(value, tx=True)
                if block:
                    auto = self.with_context(disable_auto_populate=True).create(block)
                    res = 1 if count else auto.ids
        return res

    @api.model_create_multi
    def create(self, vals_list):
        filtered_vals_list = []
        existing = self.browse()
        for vals in vals_list:
            found = self.with_context(disable_auto_populate=True).search([('hash', '=', vals['hash'])])
            if found:
                existing += found
            else:
                filtered_vals_list.append(vals)
        return super().create(filtered_vals_list) + existing


