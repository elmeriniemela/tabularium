# -*- coding: utf-8 -*-

import datetime
import logging

import bitoplens as bl
from bitoplens import ScriptError, SigVersion
from bitoplens.script import Script, opcode_description
import tinyrpc

from odoo import api, exceptions, fields, models, Command, _
from odoo.orm.domains import DomainCondition
_logger = logging.getLogger(__name__)


_BITOPLENS_FLAGS = (
    bl.ScriptVerificationFlags.P2SH
    | bl.ScriptVerificationFlags.WITNESS
    | bl.ScriptVerificationFlags.TAPROOT
    | bl.ScriptVerificationFlags.DERSIG
    | bl.ScriptVerificationFlags.NULLDUMMY
    | bl.ScriptVerificationFlags.CHECKLOCKTIMEVERIFY
    | bl.ScriptVerificationFlags.CHECKSEQUENCEVERIFY
)


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
    hex = fields.Text(readonly=True, help="The serialized transaction as hex.")
    hash = fields.Char(help="The transaction hash (differs from txid for witness transactions).")
    version = fields.Integer(help="If version is greater han or equal to 2, the sequence field for each input is used as specified in BIP68 and used in CHECKSEQUENCEVERIFY (BIP112).")
    size = fields.BigInteger(help="The serialized transaction size.")
    vsize = fields.BigInteger(help="The virtual transaction size (differs from size for witness transactions)")
    weight = fields.BigInteger(help="The transaction's weight (between vsize*4-3 and vsize*4)")
    locktime = fields.BigInteger(help="Locktime sets the earliest time a transaction can be mined in to a block. You can use locktime to make sure that a transaction is locked until a specific block height, or a point in time.")
    fee = fields.Float(help="A transaction fee is the remainder of a bitcoin transaction. Transaction fees are claimed by miners through the coinbase transaction.", digits='Bitcoin Decimal')
    blocktime = fields.Datetime(help="The block time expressed in UNIX epoch time")

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

    visualized_script = fields.Html(
        compute='_compute_visualized_script',
        sanitize=False,
    )

    is_visualized = fields.Boolean(
        compute='_compute_visualized_script',
    )

    _uniq_txid = models.Constraint('UNIQUE(txid)', 'TXID should be unique!')

    @api.model
    @api.private
    @api.readonly
    def search_fetch(self, domain, field_names, offset=0, limit=None, order=None):
        res = super().search_fetch(domain, field_names, offset=offset, limit=limit, order=order)
        condition = None
        if isinstance(domain, DomainCondition):
            condition = (domain.field_expr, domain.operator, domain.value)
        elif isinstance(domain, list) and len(domain) == 1:
            condition = domain[0]
        if not self.env.context.get('disable_auto_populate') and condition is not None:
            field, operator, value = condition
            if field == 'txid' and operator == '=':
                if not res:
                    res = self.create({'txid': value})

                res.filtered(lambda tx: not tx.block_id).refresh()

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
        force = self.env.context.get('force_tx_refresh')
        for record in self:
            if force or not record.block_id:
                try:
                    _logger.info(f"proxy.getrawtransaction({record.txid}, {True})")
                    rawtx = proxy.getrawtransaction(record.txid, True)
                except tinyrpc.protocols.jsonrpc.JSONRPCError as error:
                    raise exceptions.UserError(error.args[0])
                _logger.info("Done: %s", rawtx)
                blockhash = rawtx.get('blockhash')
                if blockhash:
                    record.block_id = Block.create({'hash': rawtx['blockhash']}).id

                record.write(self.rawtx_to_vals(rawtx))
                if force:
                    record.vin_ids.mapped('vout_tx_id').with_context(force_tx_refresh=False).refresh()


    def rawtx_to_vals(self, rawtx):
        return  {
            'in_active_chain': rawtx.get('in_active_chain'),
            'txid': rawtx['txid'],
            'hex': rawtx['hex'],
            'blocktime': datetime.datetime.fromtimestamp(rawtx['blocktime']) if 'blocktime' in rawtx else False,
            'hash': rawtx['hash'],
            'version': rawtx['version'],
            'size': rawtx['size'],
            'vsize': rawtx['vsize'],
            'weight': rawtx['weight'],
            'locktime': rawtx['locktime'],
            'fee': rawtx.get('fee', 0.0),
            'vin_ids': [
                Command.create({
                    'n': n,
                    'sequence': vin['sequence'],
                    'vout_tx_id': vin.get('txid', False),
                    'vout': vin.get('vout', False),
                    'coinbase': vin.get('coinbase', False),
                }) for n, vin in enumerate(rawtx['vin'])
            ],
            'vout_ids': [
                Command.create({
                    'n': vout['n'],
                    'value': vout['value'],
                    'script_pub_key_hex': vout['scriptPubKey']['hex'],
                    'address': vout['scriptPubKey'].get('address', False),
                    'asm': vout['scriptPubKey']['asm'],
                    'type': vout['scriptPubKey']['type'],
                }) for vout in rawtx['vout']
            ]
        }

    @api.depends(
        'hex',
        'vin_ids.n',
        'vin_ids.vout',
        'vin_ids.coinbase',
        'vin_ids.vout_tx_id',
        'vin_ids.vout_tx_id.vout_ids.script_pub_key_hex',
        'vin_ids.vout_tx_id.vout_ids.value',
        'vout_ids.n',
        'vout_ids.script_pub_key_hex',
        'vout_ids.type',
    )
    def _compute_visualized_script(self):
        template = 'bitcoin_explorer.tx_visualized_script_content'
        qweb = self.env['ir.qweb']

        for rec in self:
            input_message_kind = False
            input_message_text = False
            n_inputs = 0
            spent_outputs = []
            traces = ()
            output_scripts = [
                (txout, Script(bytes.fromhex(txout.script_pub_key_hex or '')))
                for txout in rec.vout_ids.sorted('n')
            ]
            render_vals = {
                'ScriptError': ScriptError,
                'SigVersion': SigVersion,
                'input_message_kind': False,
                'input_message_text': False,
                'mode': 'trace',
                'n_inputs': n_inputs,
                'opcode_description': opcode_description,
                'output_scripts': output_scripts,
                'traces': traces,
            }

            if not rec.hex:
                input_message_kind = 'muted'
                input_message_text = "Missing raw transaction hex."
            elif rec.vin_ids.filtered('coinbase'):
                input_message_kind = 'info'
                input_message_text = "Coinbase transactions have no input scripts to verify."
            else:
                try:
                    tx = bl.Transaction.parse(bytes.fromhex(rec.hex))
                except (IndexError, ValueError) as error:
                    input_message_kind = 'warn'
                    input_message_text = f"Unable to parse transaction hex: {error}."
                else:
                    n_inputs = len(tx.vin)
                    ordered_inputs = rec.vin_ids.sorted('n')
                    if len(ordered_inputs) != n_inputs:
                        input_message_kind = 'warn'
                        input_message_text = (
                            "Stored input data does not match the raw transaction "
                            f"({len(ordered_inputs)} stored, {n_inputs} serialized)."
                        )
                    else:
                        missing_inputs = []
                        for txin in ordered_inputs:
                            spent_output = txin.spent_output_id
                            if not spent_output or not spent_output.script_pub_key_hex:
                                missing_inputs.append(str(txin.n))
                                continue
                            spent_outputs.append(bl.TxOut(
                                int(round((spent_output.value or 0.0) * 100000000)),
                                bytes.fromhex(spent_output.script_pub_key_hex),
                            ))

                        if missing_inputs:
                            input_message_kind = 'muted'
                            input_message_text = f"Missing spent output data for input(s): {', '.join(missing_inputs)}."

            if input_message_text:
                rec.is_visualized = False
                if output_scripts:
                    render_vals['input_message_kind'] = input_message_kind
                    render_vals['input_message_text'] = input_message_text
                    render_vals['n_inputs'] = n_inputs
                    rec.visualized_script = qweb._render(template, render_vals)
                else:
                    rec.visualized_script = qweb._render(template, {
                        'message_kind': input_message_kind,
                        'message_text': input_message_text,
                        'mode': 'message',
                    })
                continue

            traces = [
                bl.run(
                    bytes(spent_output.script_pubkey),
                    tx=tx,
                    input_index=input_index,
                    spent_outputs=spent_outputs,
                    flags=_BITOPLENS_FLAGS,
                )
                for input_index, spent_output in enumerate(spent_outputs)
            ]
            render_vals['n_inputs'] = n_inputs
            render_vals['traces'] = traces
            rec.visualized_script = qweb._render(template, render_vals)
            rec.is_visualized = True


class BitcoinIn(models.Model):
    _name = 'bitcoin.tx.in'
    _description = 'Bitcoin Input'
    _rec_name = 'tx_id'
    _order = 'n asc'

    tx_id = fields.Many2one(
        comodel_name='bitcoin.tx',
        required=True,
        readonly=True,
        index=True,
        ondelete='cascade',
        help="The origin transaction whose input this is."
    )

    n = fields.Integer(
        required=True,
        index=True,
        help="An input list index within tx_id. This preserves VIN order from the raw transaction; sequence is Bitcoin nSequence, not an ordering key.",
    )

    sequence = fields.BigInteger(
        required=True,
        help="Set whether the transaction can be replaced or when it can be mined. (Locktime, Replace By Fee (RBF), Relative Locktime)"
    )

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

    _uniq_vout = models.Constraint('UNIQUE(vout_tx_id, vout)', 'Same transaction output can not be spent twice!')
    _uniq_coinbase = models.Constraint('UNIQUE(coinbase)', 'The coinbase should be unique!')
    _uniq_tx_input = models.Constraint('UNIQUE(tx_id, n)', 'The VIN index must be unique within a transaction')

    @api.depends('coinbase')
    def _compute_coinbase_ascii(self):
        for record in self:
            if record.coinbase:
                record.coinbase_ascii = bytearray.fromhex(record.coinbase).decode(encoding='ascii', errors='ignore')
            else:
                record.coinbase_ascii = False

    @api.depends('vout_tx_id', 'vout', 'vout_tx_id.vout_ids', 'vout_tx_id.vout_ids.n')
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
    script_pub_key_hex = fields.Char(required=True)
    value = fields.Float(digits='Bitcoin Decimal')

    spent_input_id = fields.Many2one(
        comodel_name='bitcoin.tx.in',
        compute='_compute_spent_input_id',
        help="The input where this UTXO was consumed. If empty, then can be spent."
    )

    _uniq_tx_output = models.Constraint('UNIQUE(tx_id, n)', 'The VOUT index must be unique within a transaction')

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
