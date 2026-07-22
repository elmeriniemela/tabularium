# -*- coding: utf-8 -*-

import datetime
import logging
import tinyrpc
import pybitcoinkernel as pbk

from markupsafe import Markup, escape

from odoo import api, exceptions, fields, models, Command, _
from odoo.orm.domains import DomainCondition
_logger = logging.getLogger(__name__)


# A palette of distinct light backgrounds. Each unique stack value is assigned
# the next unused color and keeps it everywhere it appears, so the same bytes
# are easy to follow as they move across scripts and inputs.
_DEBUG_ITEM_PALETTE = [
    "#fde0dc", "#fce8b2", "#d7f2ba", "#c6ecec", "#d4e4fb",
    "#e6d9f2", "#f9d5e5", "#e0f0d8", "#fdecc8", "#d9e7ff",
    "#f0d9c0", "#d9f0ee", "#efd9f0", "#dff0d9", "#f0dfd9",
]


def _debug_color_for(colors, key):
    """Return the color assigned to ``key``, assigning a new one on first sight."""
    if key not in colors:
        colors[key] = _DEBUG_ITEM_PALETTE[len(colors) % len(_DEBUG_ITEM_PALETTE)]
    return colors[key]


def _debug_hex_item(item, max_item_bytes=16):
    """Render a single stack item as hex, truncating long items."""
    if not item:
        return "0x"
    h = item.hex()
    if max_item_bytes is not None and len(item) > max_item_bytes:
        return f"{h[:max_item_bytes * 2]}…({len(item)} bytes)"
    return h


def _debug_stack_html(stack, colors, max_item_bytes=16):
    """Render a stack as a row of hex chips (or a muted ``empty`` marker).

    ``colors`` is a shared map from hex value to background color so identical
    items are drawn with the same color wherever they appear.
    """
    if not stack:
        return Markup('<span style="color:#9aa0a6;font-style:italic">empty</span>')
    chips = []
    for item in stack:
        bg = _debug_color_for(colors, item.hex()) if item else "#f1f3f4"
        chips.append(
            Markup(
                '<code style="background:{bg};border:1px solid rgba(0,0,0,.08);'
                'border-radius:3px;padding:1px 6px;margin:1px 3px 1px 0;'
                'display:inline-block;color:#202124;font-size:12px">{item}</code>'
            ).format(bg=bg, item=_debug_hex_item(item, max_item_bytes))
        )
    return Markup("").join(chips)


def _debug_message_box(message, kind="info"):
    """A single styled callout box for status/informational messages."""
    palette = {
        "info": ("#174ea6", "#e8f0fe", "#4285f4"),
        "warn": ("#b06000", "#fef7e0", "#f9ab00"),
        "muted": ("#3c4043", "#f1f3f4", "#9aa0a6"),
    }
    fg, bg, border = palette.get(kind, palette["info"])
    return Markup(
        '<div style="font-family:system-ui,-apple-system,sans-serif;color:{fg};'
        'background:{bg};border-left:4px solid {border};border-radius:4px;'
        'padding:10px 14px;margin:4px 0">{msg}</div>'
    ).format(fg=fg, bg=bg, border=border, msg=message)


def _debug_verdict_badge(valid):
    if valid:
        return Markup(
            '<span style="background:#e6f4ea;color:#137333;border-radius:12px;'
            'padding:2px 12px;font-weight:600;font-size:12px;'
            'letter-spacing:.5px">✓ VALID</span>'
        )
    return Markup(
        '<span style="background:#fce8e6;color:#c5221f;border-radius:12px;'
        'padding:2px 12px;font-weight:600;font-size:12px;'
        'letter-spacing:.5px">✗ INVALID</span>'
    )


def _debug_traces_to_html(traces, n_inputs):
    """Render the full per-input script-verification trace as rich HTML."""
    overall = all(t.valid for t in traces)
    colors = {}
    parts = []

    # Overall summary header.
    parts.append(
        Markup(
            '<div style="display:flex;align-items:center;gap:12px;'
            'padding:12px 16px;background:{bg};border-radius:6px;margin-bottom:12px">'
            '<span style="font-weight:600;font-size:14px;color:#202124">'
            'Transaction script verification</span>{badge}'
            '<span style="color:#5f6368;font-size:13px;margin-left:auto">'
            '{n} input(s)</span></div>'
        ).format(
            bg="#e6f4ea" if overall else "#fce8e6",
            badge=_debug_verdict_badge(overall),
            n=n_inputs,
        )
    )

    for i, trace in enumerate(traces):
        parts.append(_debug_input_html(i, trace, colors))

    return Markup(
        '<div style="font-family:system-ui,-apple-system,sans-serif;'
        'color:#202124">{}</div>'
    ).format(Markup("").join(parts))


def _debug_input_html(index, trace, colors):
    """Render one input: its verdict, error, and each script execution."""
    header = Markup(
        '<div style="display:flex;align-items:center;gap:10px;'
        'padding:8px 14px;background:#f8f9fa;border-bottom:1px solid #e0e0e0">'
        '<span style="font-weight:600;color:#202124">Input {i}</span>{badge}'
        '<span style="color:#5f6368;font-size:12px;margin-left:auto">'
        'error: <code>{err}</code></span></div>'
    ).format(i=index, badge=_debug_verdict_badge(trace.valid), err=trace.error.name)

    executions = Markup("").join(
        _debug_execution_html(idx, execution, colors)
        for idx, execution in enumerate(trace.executions)
    )

    return Markup(
        '<div style="border:1px solid #e0e0e0;border-radius:6px;'
        'overflow:hidden;margin-bottom:12px">{header}{body}</div>'
    ).format(header=header, body=executions)


def _debug_execution_html(idx, execution, colors):
    """Render a single script execution (scriptSig / scriptPubkey / …)."""
    from pybitcoinkernel.debugger import _execution_role, _seed_note

    role = _execution_role(idx, execution.sig_version)
    script_hex = execution.script.hex() or "(empty)"

    meta = [Markup('<b>#{}</b> {}').format(idx, escape(role))]
    if execution.script_type:
        meta.append(escape(execution.script_type))
    meta.append(escape(execution.sig_version.name))
    meta.append(escape(f"{len(execution.script)} bytes"))
    meta_line = Markup(
        ' <span style="color:#9aa0a6">·</span> '
    ).join(meta)

    seed = _seed_note(idx, execution.sig_version)
    seed_html = (
        Markup('<div style="color:#5f6368;font-size:12px;font-style:italic;'
               'margin-top:2px">{}</div>').format(escape(seed))
        if seed else Markup("")
    )

    rows = []
    for step in execution.steps:
        note = pbk.opcode_description(step.opcode) or ""
        row_style = "" if step.executed else "opacity:.5"
        skipped = (
            Markup(' <span style="color:#9aa0a6">(skipped)</span>')
            if not step.executed else Markup("")
        )
        rows.append(
            Markup(
                '<tr style="{rstyle}">'
                '<td style="padding:4px 10px;color:#9aa0a6;'
                'font-variant-numeric:tabular-nums;vertical-align:top">#{pos:04d}</td>'
                '<td style="padding:4px 10px;font-weight:600;color:#1a73e8;'
                'white-space:nowrap;vertical-align:top">{name}</td>'
                '<td style="padding:4px 10px;color:#5f6368;vertical-align:top">'
                '{note}{skipped}</td>'
                '<td style="padding:4px 10px;vertical-align:top">{stack}</td>'
                '</tr>'
            ).format(
                rstyle=row_style,
                pos=step.opcode_pos,
                name=escape(pbk.opcode_name(step.opcode)),
                note=escape(note),
                skipped=skipped,
                stack=_debug_stack_html(step.stack, colors),
            )
        )

    table = Markup("")
    if rows:
        table = Markup(
            '<table style="width:100%;border-collapse:collapse;font-size:12px;'
            'font-family:ui-monospace,SFMono-Regular,Menlo,monospace">'
            '<thead><tr style="text-align:left;color:#9aa0a6;'
            'border-bottom:1px solid #eee">'
            '<th style="padding:4px 10px;font-weight:500">pos</th>'
            '<th style="padding:4px 10px;font-weight:500">opcode</th>'
            '<th style="padding:4px 10px;font-weight:500">description</th>'
            '<th style="padding:4px 10px;font-weight:500">stack (before)</th>'
            '</tr></thead><tbody>{}</tbody></table>'
        ).format(Markup("").join(rows))

    end = execution.end
    result = Markup("")
    if end is not None:
        result = Markup(
            '<div style="padding:8px 14px;background:#fafafa;'
            'border-top:1px solid #eee;font-family:ui-monospace,monospace;'
            'font-size:12px"><b style="color:#5f6368">result</b> → {stack} '
            '<code style="color:#5f6368">{err}</code></div>'
        ).format(stack=_debug_stack_html(end.stack, colors), err=execution.error.name)

    return Markup(
        '<div style="padding:10px 14px;border-top:1px solid #f0f0f0">'
        '<div style="font-size:13px;margin-bottom:2px">{meta}</div>{seed}'
        '<div style="font-family:ui-monospace,monospace;font-size:11px;'
        'color:#80868b;word-break:break-all;margin:6px 0 8px">{hex}</div>'
        '{table}</div>{result}'
    ).format(meta=meta_line, seed=seed_html, hex=escape(script_hex),
             table=table, result=result)


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
    )
    def _compute_visualized_script(self):
        for rec in self:
            if not rec.hex:
                rec.visualized_script = _debug_message_box("Missing raw transaction hex.", "muted")
                continue
            if rec.vin_ids.filtered('coinbase'):
                rec.visualized_script = _debug_message_box(
                    "Coinbase transactions have no input scripts to verify.", "info")
                continue
            if not pbk.trace_available():
                rec.visualized_script = _debug_message_box(
                    "Script tracing is unavailable; rebuild libbitcoinkernel with "
                    "-DENABLE_SCRIPT_TRACE=ON.", "warn")
                continue

            tx = pbk.Transaction(bytes.fromhex(rec.hex))
            ordered_inputs = rec.vin_ids.sorted('n')
            spent_outputs = []
            missing_inputs = []
            for txin in ordered_inputs:
                spent_output = txin.spent_output_id
                if not spent_output or not spent_output.script_pub_key_hex:
                    missing_inputs.append(str(txin.n))
                    continue
                spent_outputs.append(pbk.TransactionOutput(
                    pbk.ScriptPubkey(bytes.fromhex(spent_output.script_pub_key_hex)),
                    int(round(spent_output.value * 100000000)),
                ))

            if missing_inputs:
                rec.visualized_script = _debug_message_box(
                    f"Missing spent output data for input(s): {', '.join(missing_inputs)}.",
                    "muted")
                continue

            traces = pbk.debug_transaction(tx, spent_outputs)
            rec.visualized_script = _debug_traces_to_html(traces, tx.n_inputs)


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
