# -*- coding: utf-8 -*-

import datetime
import logging
import tinyrpc

from odoo import api, exceptions, fields, models, Command, _
_logger = logging.getLogger(__name__)


class BitcoinTx(models.Model):
    _name = 'bitcoin.tx'
    _description = 'bitcoin transaction'
    _rec_name = 'txid'

    block_id = fields.Many2one(
        comodel_name='bitcoin.block',
        readonly=True,
        ondelete='cascade',
        index=True,
    )

    in_active_chain = fields.Boolean(default=True)
    txid = fields.Char(required=True, help="An identifier used to uniquely identify a particular transaction; specifically, the sha256d hash of the transaction.")
    hash = fields.Char(help="The transaction hash (differs from txid for witness transactions).")
    version = fields.Integer(help="If version is greater han or equal to 2, the sequence field for each input is used as specified in BIP68 and used in CHECKSEQUENCEVERIFY (BIP112).")
    size = fields.BigInteger(help="The serialized transaction size.")
    vsize = fields.BigInteger(help="The virtual transaction size (differs from size for witness transactions)")
    weight = fields.BigInteger(help="The transaction's weight (between vsize*4-3 and vsize*4)")
    locktime = fields.BigInteger(help="Locktime sets the earliest time a transaction can be mined in to a block. You can use locktime to make sure that a transaction is locked until a specific block height, or a point in time.")
    fee = fields.Float(help="A transaction fee is the remainder of a bitcoin transaction. Transaction fees are claimed by miners through the coinbase transaction.", digits='Bitcoin Decimal')

    vin_ids = fields.One2many(
        comodel_name='bitcoin.tx.in',
        inverse_name='tx_id',
        readonly=True,
        help="VIN: The vector of an outputs in a bitcoin transaction.",
    )

    vout_ids = fields.One2many(
        comodel_name='bitcoin.tx.out',
        inverse_name='tx_id',
        readonly=True,
        help="VOUT: The vector of an outputs in a bitcoin transaction.",
    )

    spent_input_ids = fields.One2many(
        comodel_name='bitcoin.tx.in',
        inverse_name='vout_tx_id',
        readonly=True,
        help="The inputs where outputs of this transaction are spent.",
    )

    _sql_constraints = [
        ('uniq', 'unique(txid)', 'TXID should be unique!')
    ]

    @api.model
    @api.returns('self')
    def search_fetch(self, domain, field_names, offset=0, limit=None, order=None):
        res = super().search_fetch(domain, field_names, offset=offset, limit=limit, order=order)
        if not self.env.context.get('disable_auto_populate') and len(domain) == 1:
            field, operator, value = domain[0]
            if field == 'txid' and operator == '=':
                if not res:
                    auto = self.create({'txid': value})
                    res = auto.ids

                self.browse(res).filtered(lambda tx: not tx.block_id).refresh()

        return res


    @api.model_create_multi
    def create(self, vals_list):
        txids = []
        vals_map = {}

        for vals in vals_list:
            txid = vals['txid']
            txids.append(txid)
            vals_map[txid] = vals


        existing = self.with_context(disable_auto_populate=True).search([('txid', 'in', txids)])
        for tx in existing:
            vals = vals_map[tx.txid]
            tx.write(vals)

        # Write above may have added new transactions via vout_tx_id. Redo search for existing
        existing = self.with_context(disable_auto_populate=True).search([('txid', 'in', txids)])
        existing_txids = set(existing.mapped('txid'))
        unique_vals = {}
        for vals in vals_list:
            txid = vals['txid']
            if txid not in unique_vals and txid not in existing_txids:
                unique_vals[txid] = vals

        return super().create(list(unique_vals.values())) + existing

    def refresh(self):
        proxy = self.env['ir.config_parameter'].bitcoind_proxy()
        Block = self.env['bitcoin.block'].with_context(disable_auto_populate=False)
        for record in self:
            if not record.block_id:
                try:
                    _logger.info(f"proxy.getrawtransaction({record.txid}, {True})")
                    rawtx = proxy.getrawtransaction(record.txid, True)
                except tinyrpc.protocols.jsonrpc.JSONRPCError as error:
                    raise exceptions.UserError(error.args[0])
                _logger.info("Done: %s", rawtx)
                blockhash = rawtx.get('blockhash')
                if blockhash:
                    record.block_id = Block.create({'hash': rawtx['blockhash']}).id

            record.block_id.with_context(only_txid=record.txid).refresh()



class BitcoinIn(models.Model):
    _name = 'bitcoin.tx.in'
    _description = 'Bitcoin Input'
    _rec_name = 'tx_id'
    _order = 'sequence asc'

    tx_id = fields.Many2one(
        comodel_name='bitcoin.tx',
        required=True,
        readonly=True,
        index=True,
        ondelete='cascade',
        help="The origin transaction whose input this is."
    )

    sequence = fields.BigInteger(required=True)

    vout_tx_id = fields.Many2one(
        comodel_name='bitcoin.tx',
        readonly=True,
        index=True,
        ondelete='cascade',
        help="The transaction from which 'vout' is taken to be spent."
    )

    vout = fields.Integer(
        index=True,
        help="Refers to the 'n' field of bitcoin.tx.out")

    coinbase = fields.Char()

    coinbase_ascii = fields.Char(compute="_compute_coinbase_ascii")

    spent_output_id = fields.Many2one(
        comodel_name='bitcoin.tx.out',
        compute='_compute_spent_output_id',
        help="The UTXO this input consumed. Empty for coinbase inputs.",
    )

    _sql_constraints = [
        ('uniq_vout', 'unique(vout_tx_id, vout)', 'Same transaction output can not be spent twice!'),
        ('uniq_coinbase', 'unique(coinbase)', 'The coinbase should be unique!'),
    ]

    @api.depends('coinbase')
    def _compute_coinbase_ascii(self):
        for record in self:
            if record.coinbase:
                record.coinbase_ascii = bytearray.fromhex(record.coinbase).decode(encoding='ascii', errors='ignore')
            else:
                record.coinbase_ascii = False

    def _compute_spent_output_id(self):
        Output = self.env['bitcoin.tx.out']
        for record in self:
            record.spent_output_id = Output.search([('tx_id', '=', record.vout_tx_id.id), ('n', '=', record.vout)])

    @api.model_create_multi
    def create(self, vals_list):
        Tx = self.env['bitcoin.tx'].with_context(disable_auto_populate=True)
        existing = self.browse()
        id_map = {t.txid: t.id for t in Tx.create([{'txid': v['vout_tx_id']} for v in vals_list if isinstance(v['vout_tx_id'], str)])}

        filtered_vals_list = []
        for vals in vals_list:
            if vals.get('coinbase'):
                found = self.search([('coinbase', '=', vals['coinbase'])])
            else:
                if isinstance(vals['vout_tx_id'], str):
                    vals['vout_tx_id'] = id_map[vals['vout_tx_id']]
                found = self.search([('vout_tx_id', '=', vals['vout_tx_id']),('vout', '=', vals['vout'])])
            if found:
                found.write(vals)
                existing += found
            else:
                filtered_vals_list.append(vals)

        return super().create(filtered_vals_list) + existing


class BitcoinOut(models.Model):
    _name = 'bitcoin.tx.out'
    _description = 'Bitcoin Output'
    _rec_name = 'address'
    _order = 'tx_id asc, n asc'

    tx_id = fields.Many2one(
        comodel_name='bitcoin.tx',
        required=True,
        index=True,
        readonly=True,
        ondelete='cascade',
    )

    n = fields.Integer(
        index=True,
        required=True,
        help="An output list index within tx_id, used to refer to a specific output.")
    type = fields.Char(required=True)

    address = fields.Char()
    asm = fields.Char()
    value = fields.Float(digits='Bitcoin Decimal')

    spent_input_id = fields.Many2one(
        comodel_name='bitcoin.tx.in',
        compute='_compute_spent_input_id',
        help="The input where this UTXO was consumed. If empty, then can be spent."
    )

    _sql_constraints = [
        ('uniq', 'unique(tx_id, n)', 'The VOUT index must be unique within a transaction')
    ]

    def _compute_spent_input_id(self):
        Input = self.env['bitcoin.tx.in']
        for record in self:
            record.spent_input_id = Input.search([('vout_tx_id', '=', record.tx_id.id), ('vout', '=', record.n)])

    @api.model_create_multi
    def create(self, vals_list):
        filtered_vals_list = []
        existing = self.browse()
        for vals in vals_list:
            found = self.search([('tx_id', '=', vals['tx_id']),('n', '=', vals['n'])])
            if found:
                found.write(vals)
                existing += found
            else:
                filtered_vals_list.append(vals)
        return super().create(filtered_vals_list) + existing
