# -*- coding: utf-8 -*-

import datetime
import tinyrpc

from odoo import api, exceptions, fields, models, Command, _


class BitcoinTx(models.Model):
    _name = 'bitcoin.tx'
    _description = 'bitcoin transaction'
    _rec_name = 'txid'

    block_id = fields.Many2one(
        comodel_name='bitcoin.block',
        readonly=True,
        ondelete='cascade',
    )

    in_active_chain = fields.Boolean(default=True)
    txid = fields.Char(required=True, help="An identifier used to uniquely identify a particular transaction; specifically, the sha256d hash of the transaction.")
    hash = fields.Char(help="The transaction hash (differs from txid for witness transactions).")
    version = fields.Integer()
    size = fields.Integer()
    vsize = fields.Integer()
    weight = fields.Integer()
    locktime = fields.Integer()
    fee = fields.Float(digits='Bitcoin Decimal')

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

    def rawtx_to_vals(self, rawtx):
        BitcoinTx = self.env['bitcoin.tx'].with_context(disable_auto_populate=True)
        BitcoinBlock = self.env['bitcoin.block'].with_context(disable_auto_populate=True)
        vals = {
            'txid': rawtx['txid'],
            'in_active_chain': rawtx.get('in_active_chain'),
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
                    'vout_tx_id': BitcoinTx.create({'txid': vin.get('txid')}).id if vin.get('txid') else False,
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
        if rawtx.get('blockhash'):
            vals['block_id'] = BitcoinBlock.create({'hash': rawtx['blockhash']}).id
        return vals

    @api.model
    def getrawtransaction(self, txid, blockhash=False):
        verbose = True # If false, return a string, otherwise return a json object

        proxy = self.env['ir.config_parameter'].bitcoind_proxy()

        args = [txid, verbose]
        if blockhash:
            args.append(blockhash)

        try:
            rawtx = proxy.getrawtransaction(*args)
        except tinyrpc.protocols.jsonrpc.JSONRPCError as error:
            raise exceptions.UserError(error.args[0])

        return self.rawtx_to_vals(rawtx)

    @api.model
    def _search(self, domains, offset=0, limit=None, order=None, count=False, access_rights_uid=None):
        res = super()._search(domains, offset, limit, order, count=count, access_rights_uid=access_rights_uid)
        found = res if count else len(res)
        if not self.env.context.get('disable_auto_populate') and not found and len(domains) == 1:
            field, operator, value = domains[0]
            if field == 'txid' and operator == '=':
                tx = self.getrawtransaction(value)
                if tx:
                    auto = self.with_context(disable_auto_populate=True).create(tx)
                    res = 1 if count else auto.ids
        return res


    def refresh(self):
        for record in self:
            record.write(record.getrawtransaction(record.txid, blockhash=record.block_id.hash))

    @api.model
    def create(self, vals):
        existing = self.search([('txid', '=', vals['txid'])])
        if existing:
            if not existing.fee and vals.get('fee'):
                existing.fee = vals['fee']
            return existing
        return super().create(vals)



class BitcoinIn(models.Model):
    _name = 'bitcoin.tx.in'
    _description = 'Bitcoin Input'
    _rec_name = 'tx_id'
    _order = 'sequence asc'

    tx_id = fields.Many2one(
        comodel_name='bitcoin.tx',
        required=True,
        readonly=True,
        ondelete='cascade',
        help="The origin transaction whose input this is."
    )

    sequence = fields.BigInteger(required=True)

    vout_tx_id = fields.Many2one(
        comodel_name='bitcoin.tx',
        readonly=True,
        ondelete='cascade',
        help="The transaction from which 'vout' is taken to be spent."
    )

    vout = fields.Integer(help="Refers to the 'n' field of bitcoin.tx.out")

    coinbase = fields.Char()

    _sql_constraints = [
        ('uniq', 'unique(vout_tx_id, vout)', 'Same transaction output can not be spent twice!'),
    ]

    @api.model
    def create(self, vals):
        if vals.get('coinbase'):
            existing = self.search([('coinbase', '=', vals['coinbase'])])
        else:
            existing = self.search([('vout_tx_id', '=', vals['vout_tx_id']),('vout', '=', vals['vout'])])
        if existing:
            return existing
        return super().create(vals)


class BitcoinOut(models.Model):
    _name = 'bitcoin.tx.out'
    _description = 'Bitcoin Output'
    _rec_name = 'address'
    _order = 'tx_id asc, n asc'

    tx_id = fields.Many2one(
        comodel_name='bitcoin.tx',
        required=True,
        readonly=True,
        ondelete='cascade',
    )

    n = fields.Integer(required=True, help="An output list index within tx_id, used to refer to a specific output.")
    type = fields.Char(required=True)

    address = fields.Char()
    asm = fields.Char()
    value = fields.Float(digits='Bitcoin Decimal')

    _sql_constraints = [
        ('uniq', 'unique(tx_id, n)', 'The VOUT index must be unique within a transaction')
    ]

    @api.model
    def create(self, vals):
        existing = self.search([('tx_id', '=', vals['tx_id']),('n', '=', vals['n'])])
        if existing:
            return existing
        return super().create(vals)
