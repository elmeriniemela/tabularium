import base64
from decimal import Decimal
import hashlib
import json
import re

from bitwalkit import (
    BitwalkitError, ExtendedKey, InputSequence, KeyOrigin, PSBTInput, PSBTOutput,
    SegwitSpend, address_to_script, create_psbt, derive_native_segwit,
    dust_threshold, op_return_script,
)

from odoo import api, fields, models, Command, _
from odoo.exceptions import ValidationError


def _btc(satoshis):
    return format(Decimal(satoshis) / 100_000_000, '.8f')


class BitcoinPSBT(models.Model):
    _name = 'bitcoin.psbt'
    _description = 'Generate Bitcoin PSBT'

    name = fields.Char(
        string="Filename", default="transaction.psbt", required=True,
        help=(
            "A human-readable label for this PSBT. It does not change the transaction, "
            "the fee, or any signing data. Use a name that identifies the intended payment, such as "
            "'supplier_payment_2026-09-05.psbt' or 'cold_storage_consolidation.psbt'."
        ),
    )
    rbf = fields.Boolean(
        string="Replace-by-Fee (RBF)", default=True,
        help=(
            "Signal opt-in replaceability under BIP 125. When checked, inputs use sequence "
            "0xFFFFFFFD, allowing this transaction to be fee-bumped or replaced while unconfirmed. "
            "When unchecked, inputs use final sequence 0xFFFFFFFF. Example: leave checked for "
            "standard payments so you can bump fees if mempool traffic increases."
        ),
    )

    input_ids = fields.One2many(
        'bitcoin.psbt.input', 'psbt_id', string="Inputs",
        help=(
            "Previous transaction outputs that this transaction will spend. Each row identifies one output "
            "by its transaction ID and output index, declares its full satoshi amount, and selects the wallet "
            "address whose keys should authorize the spend. You can combine inputs from several wallets. "
            "No balance, transaction history, or spent-status lookup is performed, but the same outpoint "
            "cannot appear twice. Example: add output 0 of one transaction for 30,000,000 sat and output 2 "
            "of another for 20,000,000 sat to declare 50,000,000 sat of inputs."
        ),
    )
    output_ids = fields.One2many(
        'bitcoin.psbt.output', 'psbt_id', string="Outputs",
        help=(
            "Payments created by the new transaction, including any change you want to keep. Each row "
            "specifies a destination and an amount in satoshis. Use a pasted address for a recipient or select a "
            "wallet address to include its signing metadata. Change is never added automatically: the "
            "entire difference between declared inputs and these outputs is the fee. Example: for "
            "50,000,000 sat of inputs, send 20,000,000 sat to a recipient and 29,990,000 sat to your "
            "wallet's Change branch, leaving a declared fee of 10,000 sat."
        ),
    )
    input_total = fields.Char(
        string="Declared Inputs (BTC)", compute='_compute_totals',
        help=(
            "Sum of all amounts entered in the input rows, displayed in BTC with eight decimal places. "
            "This is a total of your declarations, not the wallet's recorded balance or an independently "
            "verified amount available on the blockchain. It updates when input amounts change. "
            "Example: input amounts of 0.10000000 BTC and 0.02500000 BTC produce 0.12500000 BTC here, "
            "even if the selected wallets have no recorded balance."
        ),
    )
    output_total = fields.Char(
        string="Total Outputs (BTC)", compute='_compute_totals',
        help=(
            "Sum of all new output amounts, including recipient payments and explicitly entered change. "
            "This total excludes the transaction fee and cannot exceed the declared input total when "
            "generating a PSBT. It updates automatically as you edit the output rows. Example: a "
            "0.04000000 BTC payment plus 0.05990000 BTC of change gives an output total of 0.09990000 BTC."
        ),
    )
    fee = fields.Char(
        string="Declared Fee (BTC)", compute='_compute_totals',
        help=(
            "Declared input total minus total outputs, expressed in BTC. This is an absolute fee amount, "
            "not a fee rate in sat/vB or a recommendation based on network conditions. Its accuracy "
            "depends on entering the actual full value of every previous output. Any change you omit "
            "increases this fee. Example: 0.10000000 BTC of inputs minus 0.09990000 BTC of outputs leaves "
            "0.00010000 BTC, or 10,000 satoshis. A negative fee prevents generation; a zero fee is allowed "
            "with an advisory warning."
        ),
    )
    amount_error = fields.Char(
        compute='_compute_totals',
        help=(
            "Explains an amount or total that must be corrected before the PSBT can be generated. "
            "Amounts must be nonnegative integer satoshi values, and outputs must fit within the declared "
            "inputs. Individual amounts and transaction totals cannot exceed 21,000,000 BTC "
            "(2,100,000,000,000,000 satoshis). Clear messages do not establish "
            "that the supplied input details are correct on the blockchain."
        ),
    )
    review_warnings = fields.Text(
        string="Review Before Signing", compute='_compute_review_warnings',
        help=(
            "Advisory checks for possible mistakes: large or zero declared fees, missing explicit change, "
            "dust outputs, repeated destinations, and wallet outputs outside the configured address window. "
            "These warnings do not block generation or verify chain state. Large-fee warnings start at "
            "0.001 BTC or 1% of declared inputs; these are review thresholds, not recommended fees. "
            "Example: declaring a 1 BTC input and only a 0.5 BTC payment warns that the remaining 0.5 BTC "
            "is the fee and that you may have forgotten change."
        ),
    )
    generated_psbt = fields.Binary(
        readonly=True, attachment=False,
        help=(
            "Internal storage for the most recently generated unsigned PSBT, encoded by Odoo as binary "
            "field data. It is retained with this PSBT and is used to prepare the downloadable "
            "file and Base64 text. Use those export fields to obtain a result matching the current "
            "transaction details. Example: generating a draft stores its PSBT here; changing a payment "
            "afterward hides the public export until a matching PSBT is generated."
        ),
    )
    generated_fingerprint = fields.Char(
        readonly=True,
        help=(
            "Internal SHA-256 fingerprint of the transaction rows and wallet key settings used for the "
            "stored PSBT. The wizard compares this fingerprint with its current settings to avoid "
            "offering an outdated export. It is not a transaction ID or a master key fingerprint. "
            "Example: changing an output from 0.01000000 BTC to 0.02000000 BTC changes the fingerprint "
            "and makes the previous export unavailable for the edited draft."
        ),
    )
    psbt_binary = fields.Binary(
        string="PSBT File", compute='_compute_result', attachment=False,
        help=(
            "Download the generated unsigned transaction as a binary .psbt file for a compatible external "
            "signer. The file includes declared previous-output values, wallet key derivations, extended "
            "public keys, and any required multisig witness scripts. Generation does not sign or broadcast "
            "the transaction. The download is available only when the stored export matches the current "
            "draft. Example: click transaction.psbt to save the file, then import it into your signing "
            "wallet and verify every destination, amount, and fee before signing."
        ),
    )
    psbt_base64 = fields.Text(
        string="PSBT Base64", compute='_compute_result',
        help=(
            "The same generated PSBT as the downloadable file, represented as Base64 text for software "
            "that accepts pasted PSBTs. Copy the complete value, including any trailing equals signs; "
            "Base64 is an encoding, not encryption. The text includes public wallet metadata and should "
            "only be shared with intended signers. Example: use Copy Base64 and paste the full string "
            "beginning with cHNidP into a compatible wallet's PSBT import field."
        ),
    )

    @api.model
    def default_get(self, field_names):
        values = super().default_get(field_names)
        if 'input_ids' in field_names and 'input_ids' not in values:
            source = {}
            if self.env.context.get('default_source_wallet_id'):
                source['wallet_id'] = self.env.context['default_source_wallet_id']
            if self.env.context.get('default_source_address_id'):
                address = self.env['bitcoin.wallet.address'].browse(self.env.context['default_source_address_id']).exists()
                if address:
                    source.update(wallet_id=address.wallet_id.id, branch=address.atype, address_index=address.index)
            values['input_ids'] = [Command.create(source)]
        if 'output_ids' in field_names and 'output_ids' not in values:
            values['output_ids'] = [Command.create({})]
        return values

    @api.depends('input_ids.sats', 'output_ids.sats')
    def _compute_totals(self):
        for wizard in self:
            wizard.input_total = wizard.output_total = wizard.fee = False
            wizard.amount_error = False
            lines = list(wizard.input_ids) + list(wizard.output_ids)
            if any(line.sats < 0 for line in lines):
                wizard.amount_error = _("Amount must be nonnegative.")
                continue
            if any(line.sats > 21_000_000 * 100_000_000 for line in lines):
                wizard.amount_error = _("Amount cannot exceed 21,000,000 BTC.")
                continue
            inputs = sum(line.sats for line in wizard.input_ids)
            outputs = sum(line.sats for line in wizard.output_ids)
            wizard.input_total = _btc(inputs)
            wizard.output_total = _btc(outputs)
            wizard.fee = _btc(inputs - outputs)
            if outputs > inputs:
                wizard.amount_error = _("Total outputs exceed the declared input amounts.")
            elif inputs > 21_000_000 * 100_000_000:
                wizard.amount_error = _("Total input amount cannot exceed 21,000,000 BTC.")

    @api.depends(
        'input_ids.sats', 'input_ids.wallet_id',
        'output_ids.sats', 'output_ids.destination_type', 'output_ids.address',
        'output_ids.wallet_id', 'output_ids.branch', 'output_ids.address_index',
        'output_ids.op_return_format', 'output_ids.op_return_data',
        'output_ids.sequence', 'output_ids.derived_address', 'output_ids.wallet_id.address_amount',
    )
    def _compute_review_warnings(self):
        for wizard in self:
            warnings = []
            if not wizard.amount_error:
                inputs = sum(line.sats for line in wizard.input_ids)
                outputs = sum(line.sats for line in wizard.output_ids)
                fee = inputs - outputs
                # Review heuristics, deliberately independent of mempool fee rates.
                if fee > 0 and (fee >= 100_000 or fee * 100 >= inputs):
                    warnings.append(_(
                        "Large declared fee: %(fee)s BTC (%(sats)s sat). Review fees of at least "
                        "0.001 BTC or 1%% of declared inputs. Any omitted change becomes the fee.",
                        fee=_btc(fee), sats=fee,
                    ))
                if wizard.input_ids and wizard.output_ids and fee == 0:
                    warnings.append(_("The declared fee is zero. A signed transaction may not be relayed or mined."))
                has_change = any(
                    line.destination_type == 'wallet' and line.branch == '1'
                    and line.wallet_id in wizard.input_ids.wallet_id
                    for line in wizard.output_ids
                )
                if fee > 0 and not has_change:
                    warnings.append(_(
                        "No explicit change output to an input wallet is declared. "
                        "Confirm a full spend is intended, or add change; the entire remainder is the fee."
                    ))

            destinations = {}
            op_return_count = 0
            for number, line in enumerate(wizard.output_ids.sorted('sequence'), 1):
                if line.destination_type == 'wallet' and line.wallet_id and line.address_index >= line.wallet_id.address_amount:
                    warnings.append(_(
                        "Output %(row)s uses wallet address index %(index)s, outside its configured "
                        "address window. Make sure your receiving and recovery wallets scan this index.",
                        row=number, index=line.address_index,
                    ))
                try:
                    script = line._script()
                except (BitwalkitError, ValidationError, ValueError, IndexError):
                    continue
                amount = line.sats
                if line.destination_type == 'op_return':
                    op_return_count += 1
                    if amount > 0:
                        warnings.append(_(
                            "Output %(row)s is an OP_RETURN output with %(amount)s BTC (%(sats)s sat). "
                            "Any funds sent to an OP_RETURN output are provably unspendable and permanently burned.",
                            row=number, amount=_btc(amount), sats=amount,
                        ))
                    if len(script) > 83:
                        warnings.append(_(
                            "Output %(row)s OP_RETURN script is %(bytes)s bytes, exceeding the standard "
                            "83-byte relay limit. Standard nodes may not relay this transaction.",
                            row=number, bytes=len(script),
                        ))
                else:
                    threshold = dust_threshold(script)
                    if amount < threshold:
                        warnings.append(_(
                            "Output %(row)s is %(amount)s sat, below the %(threshold)s sat dust threshold "
                            "at the 3000 sat/kvB policy baseline. Relay policies vary; this output may be rejected.",
                            row=number, amount=amount, threshold=threshold,
                        ))
                if script in destinations:
                    warnings.append(_(
                        "Outputs %(first)s and %(second)s pay the same destination. Check for an accidental duplicate payment.",
                        first=destinations[script], second=number,
                    ))
                else:
                    destinations[script] = number
            if op_return_count > 1:
                warnings.append(_(
                    "Transaction contains multiple OP_RETURN outputs. Standard Bitcoin relay policy "
                    "allows at most one OP_RETURN output per transaction; transactions with multiple "
                    "OP_RETURN outputs may not be relayed."
                ))
            wizard.review_warnings = '\n\n'.join(warnings) or False

    @api.depends(
        'generated_psbt', 'generated_fingerprint', 'rbf',
        'input_ids', 'output_ids',
        'input_ids.sequence', 'input_ids.txid', 'input_ids.output_index', 'input_ids.sats',
        'input_ids.wallet_id', 'input_ids.branch', 'input_ids.address_index',
        'output_ids.sequence', 'output_ids.sats', 'output_ids.destination_type', 'output_ids.address',
        'output_ids.wallet_id', 'output_ids.branch', 'output_ids.address_index',
        'output_ids.op_return_format', 'output_ids.op_return_data',
        'input_ids.wallet_id.sigs_required', 'output_ids.wallet_id.sigs_required',
        'input_ids.wallet_id.key_ids', 'output_ids.wallet_id.key_ids',
        'input_ids.wallet_id.key_ids.key_id.wif', 'output_ids.wallet_id.key_ids.key_id.wif',
        'input_ids.wallet_id.key_ids.key_id.script_type', 'output_ids.wallet_id.key_ids.key_id.script_type',
        'input_ids.wallet_id.key_ids.key_id.real_parent_fingerprint',
        'output_ids.wallet_id.key_ids.key_id.real_parent_fingerprint',
        'input_ids.wallet_id.key_ids.key_id.real_derivation_path',
        'output_ids.wallet_id.key_ids.key_id.real_derivation_path',
    )
    def _compute_result(self):
        for wizard in self:
            wizard.psbt_binary = False
            wizard.psbt_base64 = False
            if wizard.generated_fingerprint and wizard.generated_fingerprint == wizard._transaction_fingerprint():
                encoded = wizard.with_context(bin_size=False).generated_psbt
                wizard.psbt_binary = encoded
                wizard.psbt_base64 = encoded.decode('ascii') if encoded else False

    def _transaction_fingerprint(self):
        """Check fresh wallet metadata too: regular-to-wallet dependency triggers are incomplete here."""
        self.ensure_one()

        def wallet_spec(line):
            wallet = line.wallet_id
            return [wallet.id, wallet.sigs_required, line.branch, line.address_index, [
                [key.wif, key.script_type, key.real_parent_fingerprint, key.real_derivation_path]
                for key in wallet.key_ids.key_id
            ]]

        inputs = [[line.txid, line.output_index, line.sats, wallet_spec(line)]
                  for line in self.input_ids.sorted('sequence')]
        outputs = [[line.destination_type, line.address, line.sats,
                    line.op_return_format, line.op_return_data,
                    wallet_spec(line) if line.destination_type == 'wallet' else None]
                   for line in self.output_ids.sorted('sequence')]
        return hashlib.sha256(json.dumps([self.rbf, inputs, outputs], sort_keys=True).encode()).hexdigest()

    def action_generate(self):
        self.ensure_one()
        if self.amount_error:
            raise ValidationError(self.amount_error)
        sequence = InputSequence.RBF if self.rbf else InputSequence.FINAL
        inputs = [PSBTInput(
            (line.txid or '').strip(), line.output_index, line.sats,
            line._spend(), sequence=sequence,
        ) for line in self.input_ids.sorted('sequence')]
        outputs = []
        for line in self.output_ids.sorted('sequence'):
            spend = line._spend() if line.destination_type == 'wallet' else None
            outputs.append(PSBTOutput(line.sats, line._script(), spend))
        encoded = base64.b64encode(create_psbt(inputs, outputs))
        self.write({'generated_psbt': encoded, 'generated_fingerprint': self._transaction_fingerprint()})
        return {
            'type': 'ir.actions.act_window', 'res_model': self._name,
            'res_id': self.id, 'view_mode': 'form', 'target': 'fullscreen',
            'name': _("Generate PSBT"),
        }


class BitcoinPSBTWalletLine(models.AbstractModel):
    _name = 'bitcoin.psbt.wallet.line'
    _description = 'PSBT Wallet Derivation'

    sequence = fields.Integer(
        default=10,
        help=(
            "Controls this row's position within the transaction's input list or output list. Lower "
            "values come first; use the drag handle to reorder rows in the wizard. This is a display "
            "and serialization order, not the Bitcoin input sequence value used for locktime or fee "
            "replacement. Example: rows ordered 10 and 20 appear first and second respectively. "
            "Reordering transaction rows requires a matching regenerated export."
        ),
    )
    wallet_id = fields.Many2one(
        'bitcoin.wallet', string="Wallet", ondelete='cascade', context={'active_test': False},
        help=(
            "Watch-only wallet whose extended public keys determine this row's address and signing "
            "metadata. The branch and address index select a child address directly; a balance and "
            "refreshed address history are unnecessary. Supported wallet configurations are native "
            "SegWit single-signature and multisig, with complete key origins for account keys. "
            "Example: select Treasury Savings, then Change and index 5 to derive that wallet's /1/5 address."
        ),
    )
    branch = fields.Selection(
        [('0', 'Receiving'), ('1', 'Change')], required=True, default='0',
        help=(
            "Selects the address branch below the wallet's extended public keys: Receiving appends /0 "
            "and Change appends /1 before the address index. For an input, choose the branch of the "
            "address that received the previous output. For a wallet output, Change normally returns "
            "the unused amount to your wallet. Selecting it does not calculate or add change automatically. "
            "Example: Change with address index 5 appends /1/5 to an account path, such as "
            "m/84'/0'/0'/1/5."
        ),
    )
    address_index = fields.Integer(
        default=0, required=True,
        help=(
            "Zero-based child address number within the selected Receiving or Change branch. This is "
            "a wallet derivation index, not the previous transaction's output index. Values from 0 to "
            "2,147,483,647 are supported, and the address is derived without requiring a stored address "
            "record. Example: Receiving with index 5 selects /0/5, the sixth address on that branch. "
            "If you send to a high index, make sure your receiving and recovery wallets scan far enough "
            "to discover it."
        ),
    )
    sats = fields.BigInteger(
        string="Satoshis", default=0, required=True,
        help=(
            "Satoshi amount assigned to this row (1 BTC = 100,000,000 satoshis). "
            "Inputs declare the full previous-output value; outputs specify the "
            "value sent to their destination. Must be a nonnegative integer up to "
            "2,100,000,000,000,000 satoshis (21,000,000 BTC). "
            "Example: enter 100000 for 0.001 BTC, or 1 for one satoshi."
        ),
    )
    derived_address = fields.Char(
        compute='_compute_derived_address', string="Wallet Address",
        help=(
            "Mainnet address calculated from the selected wallet, branch, and address index. It is "
            "read-only because changing those choices determines the address. For an input, verify "
            "that this address matches the previous output you intend to spend; for a wallet output, "
            "it is the destination that will receive the entered amount. Example: selecting Receiving "
            "and index 0 displays the wallet's first receiving address. Deriving an address does not "
            "prove that an output exists or is unspent."
        ),
    )
    derivation_error = fields.Char(
        compute='_compute_derived_address',
        help=(
            "Explains why the selected wallet address or its signing metadata cannot be derived. "
            "Possible causes include an unsupported script type, missing account-key origin details, "
            "an origin path that does not match the extended key, or an invalid address index. Correct "
            "the row or the wallet's key settings before generating an input or wallet output. "
            "Example: an account key exported at m/84'/0'/0' needs that full origin path and its "
            "master key fingerprint; omitting them produces a derivation error."
        ),
    )

    def _spend(self) -> SegwitSpend:
        """Derive signing metadata and verify address against wallet records.

        :return SegwitSpend: Native SegWit spend object containing address,
            scriptPubKey, BIP32 derivations, and witness script needed for PSBT generation.
        """
        self.ensure_one()
        wallet = self.wallet_id
        if not wallet:
            raise ValidationError(_("Select a wallet for this row."))
        keys = wallet.key_ids.key_id
        script_type = 'p2wpkh' if len(keys) == 1 else 'p2wsh'
        if not keys or any(key.script_type != script_type for key in keys):
            raise ValidationError(_("PSBT inputs and wallet outputs require native SegWit single-signature or multisig keys."))
        origins = []
        for key in keys:
            parsed = ExtendedKey.parse(key.wif)
            if parsed.network != 'mainnet':
                raise ValidationError(_("Use mainnet extended public keys."))

            key_label = key.display_name or key.name or key.wif[:16]
            if not key.real_derivation_path:
                raise ValidationError(_("Add derivation path for %s.") % key_label)

            if not key.real_parent_fingerprint:
                raise ValidationError(_("Add parent fingerprint for %s.") % key_label)

            origin = KeyOrigin.parse(key.real_parent_fingerprint, key.real_derivation_path)
            origins.append((parsed, origin))
        spend = derive_native_segwit(
            origins, int(self.branch), self.address_index,
            threshold=wallet.sigs_required if len(keys) > 1 else 1,
        )
        wallet_addr = wallet.address_ids.filtered(
            lambda a: a.atype == self.branch and a.index == self.address_index
        )
        if wallet_addr and wallet_addr.address != spend.address:
            raise ValidationError(
                _("Derived address %(derived)s does not match wallet address %(wallet)s for branch %(branch)s, index %(index)s.")
                % {
                    'derived': spend.address,
                    'wallet': wallet_addr.address,
                    'branch': self.branch,
                    'index': self.address_index,
                }
            )
        return spend

    @api.depends(
        'wallet_id', 'branch', 'address_index', 'wallet_id.sigs_required', 'wallet_id.key_ids',
        'wallet_id.key_ids.key_id.wif', 'wallet_id.key_ids.key_id.script_type',
        'wallet_id.key_ids.key_id.real_parent_fingerprint', 'wallet_id.key_ids.key_id.real_derivation_path',
        'wallet_id.address_ids.address', 'wallet_id.address_ids.atype', 'wallet_id.address_ids.index',
    )
    def _compute_derived_address(self):
        for line in self:
            line.derived_address = line.derivation_error = False
            if line.wallet_id:
                try:
                    line.derived_address = line._spend().address
                except (BitwalkitError, ValidationError, ValueError) as error:
                    line.derivation_error = str(error)


class BitcoinPSBTInput(models.Model):
    _name = 'bitcoin.psbt.input'
    _inherit = 'bitcoin.psbt.wallet.line'
    _description = 'PSBT Input'
    _order = 'sequence, id'

    psbt_id = fields.Many2one(
        'bitcoin.psbt', required=True, ondelete='cascade',
        help=(
            "PSBT that owns this input row. The wizard assigns this link automatically "
            "so the row contributes to the correct input total and generated transaction. Deleting "
            "the draft also deletes its input rows. Example: adding an input in the currently open "
            "Generate PSBT dialog links it to that draft, not to another open PSBT draft."
        ),
    )
    wallet_id = fields.Many2one(
        required=True,
        help=(
            "Wallet whose keys should authorize spending this previous output. Its extended public "
            "keys, together with the Receiving/Change branch and address index, determine the source "
            "script and the derivation metadata supplied to the signer. Selecting a wallet does not "
            "select coins, verify ownership on-chain, or require a balance. Use a supported native "
            "SegWit wallet with complete account-key origins. Example: if a previous payment went to "
            "Treasury Savings at /0/7, select Treasury Savings, Receiving, and address index 7."
        ),
    )
    sats = fields.BigInteger(
        help=(
            "Declare the full satoshi value of the previous output identified by this row's txid and "
            "output index, even when you intend to pay only part of it to a recipient. This manually "
            "entered value is included in the PSBT and used to calculate the declared fee; it is not "
            "looked up or checked against a balance. Example: to spend a 50,000,000 sat output and pay "
            "20,000,000 sat, enter 50000000 here, then enter the payment and any change as output rows."
        ),
    )
    txid = fields.Char(
        string="Previous Transaction ID", required=True,
        help=(
            "The 64 hexadecimal characters of the previous transaction's txid, as displayed by a "
            "trusted explorer or wallet. Combined with Previous Output Index, it identifies the exact "
            "output to spend. Use txid rather than wtxid, and do not reverse its displayed byte order. "
            "The generator checks its format but does not fetch the transaction. Example: a dummy "
            "txid consisting of 'ab' repeated 32 times is accepted for an offline experiment; an actual "
            "spend needs the real transaction ID."
        ),
    )
    output_index = fields.BigInteger(
        string="Previous Output Index", required=True, default=0,
        help=(
            "Zero-based vout position of the output within the previous transaction: 0 is its first "
            "output, 1 its second, and so on. This is different from the wallet Address Index, which "
            "selects a derived address. Values from 0 to 4,294,967,295 can be encoded, but an actual "
            "spend must reference an output that exists. Example: to spend the third output of the "
            "transaction identified by txid, enter 2 here and verify that output's full amount and "
            "source address against the other fields in this row."
        ),
    )


class BitcoinPSBTOutput(models.Model):
    _name = 'bitcoin.psbt.output'
    _inherit = 'bitcoin.psbt.wallet.line'
    _description = 'PSBT Output'
    _order = 'sequence, id'

    psbt_id = fields.Many2one(
        'bitcoin.psbt', required=True, ondelete='cascade',
        help=(
            "PSBT that owns this output row. The wizard sets this link automatically "
            "so the payment is included in that draft's output total and serialized transaction. "
            "Deleting the draft also deletes its output rows. Example: a recipient payment and a "
            "change row added in the same Generate PSBT dialog both belong to this linked draft."
        ),
    )
    destination_type = fields.Selection(
        [('address', 'Address'), ('wallet', 'Wallet'), ('op_return', 'OP_RETURN')], default='address', required=True,
        help=(
            "Chooses how this output's destination is specified. Address uses the mainnet address "
            "you paste into Destination Address. Wallet derives an address from a selected wallet, "
            "branch, and index and includes that wallet's key derivations and any multisig witness "
            "script in the PSBT. OP_RETURN creates a provably unspendable data carrier output with "
            "the specified text or hexadecimal payload. Only the selected mode's destination is used. "
            "Example: choose Address for a recipient, Wallet for your change, or OP_RETURN to embed "
            "an arbitrary data commitment."
        ),
    )
    op_return_format = fields.Selection(
        [('text', 'ASCII-text'), ('hex', 'Hex')], default='text', required=True, string="Data Format",
        help=(
            "Encoding format used to interpret the OP_RETURN data payload. Text encodes the string as "
            "ASCII bytes. Hex parses hexadecimal characters into raw bytes. Example: entering 'hello' "
            "in Text mode produces bytes 68656c6c6f, while entering '68656c6c6f' in Hex mode produces "
            "the same 5 bytes. Incomplete or invalid hex strings are rejected during generation."
        ),
    )
    op_return_data = fields.Char(
        string="OP_RETURN Data",
        help=(
            "Payload data embedded in this OP_RETURN script. When Data Format is Text, enter plain "
            "text encoded as ASCII. When Data Format is Hex, enter an even number of hexadecimal "
            "digits. Standard Bitcoin network relay policy allows at most 80 bytes of data (83 bytes "
            "total script size). Example: enter 'invoice-12345' in Text format or '4f4d4e49' in Hex "
            "format. Leaving this empty creates a bare OP_RETURN output with no pushed data."
        ),
    )
    wallet_id = fields.Many2one(
        help=(
            "Wallet that will receive this output when Destination Type is Wallet. Its keys, branch, "
            "and address index determine the destination and the metadata included for external "
            "signers. This can be an input wallet receiving change or a different wallet receiving "
            "a transfer; choosing it never calculates the amount automatically. This field is ignored "
            "in Address mode. Example: select Treasury Savings and its Change branch to return "
            "0.29990000 BTC from a 0.5 BTC input after a 0.2 BTC payment and 0.0001 BTC fee."
        ),
    )
    sats = fields.BigInteger(
        help=(
            "Satoshi value to send to this output's destination. Enter recipient payments and change "
            "as separate rows; there is no automatic change calculation. The combined output amounts "
            "must not exceed the declared input total. Example: enter 20000000 for a 20,000,000 sat payment, "
            "then 29990000 on a change row when spending a 50,000,000 sat input with a 10,000 sat fee. "
            "Zero and dust amounts can be exported with warnings, but may not be accepted for relay."
        ),
    )
    address = fields.Char(
        string="Destination Address",
        help=(
            "Mainnet Bitcoin address that receives this output when Destination Type is Address. "
            "The generator validates and converts it to an output script, but it does not verify "
            "who controls the address. Testnet and regtest addresses are rejected. This field is "
            "ignored in Wallet mode, where Wallet Address supplies the destination instead. "
            "Example: a published test-vector address has the form "
            "bc1qcr8te4kr609gcawutmrza0j4xv80jy8z306fyu; use your intended recipient's verified "
            "address rather than this example, and confirm it on the signing device."
        ),
    )

    def _script(self) -> bytes:
        """Construct the output scriptPubKey based on destination type.

        :return bytes: Serialized Bitcoin script for this output (P2WPKH/P2WSH
            for wallet/address destinations, or OP_RETURN data push).
        """
        self.ensure_one()
        match self.destination_type:
            case 'wallet':
                return address_to_script(self._spend().address, network='mainnet')
            case 'address':
                return address_to_script((self.address or '').strip(), network='mainnet')
            case 'op_return':
                raw = self.op_return_data or ''
                match self.op_return_format:
                    case 'hex':
                        data = bytes.fromhex(raw)
                    case 'text':
                        data = raw.encode('ascii')
                if len(data) > 10_000:
                    raise ValidationError(_("OP_RETURN data exceeds maximum script size of 10,000 bytes."))
                return op_return_script(data)
            case _: # pragma: no cover
                raise ValueError(f"Invalid {self.destination_type=}")
