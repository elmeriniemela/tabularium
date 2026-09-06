import base64
from unittest.mock import patch

from bitwalkit import ExtendedKey, InputSequence, derive_native_segwit

from odoo import Command
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import Form, TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestBitcoinPSBT(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.root = ExtendedKey.parse(
            'xpub661MyMwAqRbcGFeMhhkrJL6Yj3YKQFNZQSM2BAvoMmhdjNKBh43n5v3c4YT5dFtjkirfhqQH'
            'Md22br7cHAQXAV8cZdicedZJkNweja4WWBK'
        )
        cls.key = cls.env['bitcoin.key'].create({
            'wif': cls.root.serialize(),
            'witness_type': 'segwit',
            'real_parent_fingerprint': cls.root.fingerprint.hex(),
            'real_derivation_path': 'm',
        })
        cls.wallet = cls.env['bitcoin.wallet'].create({
            'name': 'Empty PSBT wallet', 'key_ids': [Command.create({'key_id': cls.key.id})],
        })
        cls.destination = derive_native_segwit([(cls.root, None)], 0, 12).address

    def _wizard(self, **overrides):
        values = {
            'input_ids': [Command.create({
                'wallet_id': self.wallet.id, 'txid': 'ab' * 32, 'output_index': 7,
                'address_index': 999, 'sats': 123456789,
            })],
            'output_ids': [Command.create({'address': self.destination, 'sats': 123450000})],
        }
        values.update(overrides)
        return self.env['bitcoin.psbt'].create(values)

    def test_psbt_drafts_are_persistent_and_list_action_is_available(self):
        self.assertFalse(self.env['bitcoin.psbt']._transient)
        self.assertFalse(self.env['bitcoin.psbt.input']._transient)
        self.assertFalse(self.env['bitcoin.psbt.output']._transient)
        draft = self._wizard()
        self.assertEqual(draft.name, 'transaction.psbt')
        self.assertTrue(self.env.ref('bitcoin_treasury.action_psbt_list').read()[0]['res_model'] == 'bitcoin.psbt')
        self.assertEqual(self.env.ref('bitcoin_treasury.action_psbt_list').view_mode, 'list,form')

    def test_zero_balance_unknown_outpoint_and_no_network(self):
        wizard = self._wizard()
        self.assertEqual(self.wallet.balance, 0)
        self.assertFalse(self.wallet.address_ids)
        with patch('bitwalkit.ChainQuery.__init__', side_effect=AssertionError('Chain query')), \
             patch('bitwalkit.NodeRPC.__init__', side_effect=AssertionError('Node query')), \
             patch.object(type(self.env['bitcoin.tx']), 'search', side_effect=AssertionError('Transaction search')):
            wizard.action_generate()
        self.assertEqual(wizard.input_total, '1.23456789')
        self.assertEqual(wizard.fee, '0.00006789')
        raw = base64.b64decode(wizard.psbt_binary)
        self.assertTrue(raw.startswith(b'psbt\xff'))
        self.assertEqual(raw, base64.b64decode(wizard.psbt_base64))
        self.assertEqual(wizard.name, 'transaction.psbt')
        self.assertFalse(self.wallet.address_ids)

    def test_spent_output_uses_manually_declared_amount(self):
        tx_model = self.env['bitcoin.tx'].with_context(disable_auto_populate=True)
        previous = tx_model.create({
            'txid': 'ab' * 32,
            'vout_ids': [Command.create({'n': 7, 'value': 0.1, 'type': 'witness_v0_keyhash',
                                         'address': self.destination, 'script_pub_key_hex': '00', 'asm': 'asm'})],
        })
        tx_model.create({'txid': 'cd' * 32, 'vin_ids': [Command.create({
            'n': 0, 'sequence': InputSequence.FINAL, 'vout_tx_id': previous.id, 'vout': 7,
        })]})
        wizard = self._wizard()
        wizard.action_generate()
        self.assertTrue(wizard.psbt_binary)
        self.assertEqual(wizard.input_total, '1.23456789')

    def test_multisig_multiple_wallets_and_explicit_change(self):
        keys = self.env['bitcoin.key']
        for index in range(3):
            keys |= keys.create({
                'wif': self.root.child(index).serialize(), 'witness_type': 'segwit', 'multisig': True,
                'real_parent_fingerprint': self.root.fingerprint.hex(), 'real_derivation_path': 'm/%s' % index,
            })
        multisig = self.env['bitcoin.wallet'].create({
            'name': 'Multisig', 'sigs_required': 2,
            'key_ids': [Command.create({'key_id': key.id}) for key in keys],
        })
        wizard = self._wizard()
        wizard.write({
            'input_ids': [Command.create({'wallet_id': multisig.id, 'txid': 'cd' * 32, 'sats': 100000000})],
            'output_ids': [Command.create({'destination_type': 'wallet', 'wallet_id': multisig.id,
                                           'branch': '1', 'address_index': 1234, 'sats': 100000000})],
        })
        wizard.action_generate()
        self.assertEqual(wizard.fee, '0.00006789')
        raw = base64.b64decode(wizard.psbt_binary)
        spend = wizard.input_ids[1]._spend()
        change = wizard.output_ids[1]._spend()
        self.assertIn(spend.witness_script, raw)
        self.assertIn(change.witness_script, raw)
        for pubkey, origin in change.derivations:
            self.assertIn(b'\x02' + pubkey, raw)
            self.assertIn(origin.serialize(), raw)

    def test_invalid_amounts_and_totals(self):
        wizard = self._wizard()
        wizard.output_ids.sats = -1
        self.assertTrue(wizard.amount_error)
        with self.assertRaises(ValidationError):
            wizard.action_generate()

        wizard.output_ids.sats = 21_000_000 * 100_000_000 + 1
        self.assertTrue(wizard.amount_error)
        with self.assertRaises(ValidationError):
            wizard.action_generate()

        wizard.output_ids.sats = 200_000_000
        self.assertTrue(wizard.amount_error)
        with self.assertRaises(ValidationError):
            wizard.action_generate()

        wizard.output_ids.sats = wizard.input_ids.sats
        wizard.action_generate()
        self.assertEqual(wizard.fee, '0.00000000')

    def test_missing_origin_and_unsupported_keys(self):
        wizard = self._wizard()
        self.key.wif = self.root.child(1).serialize()
        self.assertTrue(wizard.input_ids.derivation_error)
        with self.assertRaises(Exception):
            wizard.action_generate()
        self.key.write({'real_parent_fingerprint': self.root.fingerprint.hex(), 'real_derivation_path': 'm/1'})
        wizard.action_generate()
        self.key.witness_type = 'legacy'
        with self.assertRaises(Exception):
            wizard.action_generate()

    def test_invalid_transaction_details(self):
        wizard = self._wizard()
        for field, value in [('txid', 'z' * 64), ('output_index', -1), ('output_index', 2**32),
                             ('address_index', -1)]:
            line = wizard.input_ids
            old = line[field]
            line[field] = value
            with self.assertRaises(Exception):
                wizard.action_generate()
            line[field] = old
        wizard.output_ids.address = 'invalid'
        with self.assertRaises(Exception):
            wizard.action_generate()
        wizard.output_ids.address = self.destination
        wizard.input_ids.copy({'psbt_id': wizard.id})
        with self.assertRaises(Exception):
            wizard.action_generate()

    def test_export_invalidation_including_direct_line_edits(self):
        wizard = self._wizard()
        wizard.action_generate()
        self.assertTrue(wizard.psbt_binary)
        wizard.input_ids.sats = 200000000
        self.assertFalse(wizard.psbt_binary)
        self.assertFalse(wizard.psbt_base64)
        wizard.action_generate()
        wizard.output_ids.address = derive_native_segwit([(self.root, None)], 0, 13).address
        self.assertFalse(wizard.psbt_binary)
        wizard.action_generate()
        self.key.wif = self.root.child(1).serialize()
        # Simulate a fresh download/read request after another form changed a key.
        wizard.invalidate_recordset(['psbt_binary', 'psbt_base64'])
        self.assertFalse(wizard.psbt_binary)
        self.assertFalse(wizard.psbt_base64)

    def test_row_deletion_invalidates_export(self):
        wizard = self._wizard()
        wizard.action_generate()
        wizard.input_ids.unlink()
        self.assertFalse(wizard.psbt_binary)
        with self.assertRaises(Exception):
            wizard.action_generate()

    def test_wallet_and_address_defaults_and_form_edit(self):
        model = self.env['bitcoin.psbt'].with_context(default_source_wallet_id=self.wallet.id)
        with Form(model) as form:
            with form.input_ids.edit(0) as line:
                self.assertEqual(line.wallet_id, self.wallet)
                line.txid = 'ab' * 32
                line.sats = 100000000
            with form.output_ids.edit(0) as line:
                line.address = self.destination
                line.sats = 99900000
            wizard = form.save()
        wizard.action_generate()
        with Form(wizard) as form:
            with form.input_ids.edit(0) as line:
                line.sats = 200000000
            self.assertFalse(form.psbt_binary)
        self.wallet.address_amount = 1
        self.wallet.refresh_addresses()
        address = self.wallet.address_ids.filtered(lambda a: a.atype == '1')
        values = self.env['bitcoin.psbt'].with_context(default_source_address_id=address.id).default_get(['input_ids'])
        self.assertEqual(values['input_ids'][0][2], {
            'wallet_id': self.wallet.id, 'branch': '1', 'address_index': 0,
        })

    def test_access_and_transient_ownership(self):
        author = new_test_user(self.env, login='psbt_author', groups='base.group_user,bitcoin_explorer.group_bitcoin_user')
        other = new_test_user(self.env, login='psbt_other', groups='base.group_user,bitcoin_explorer.group_bitcoin_user')
        unauthorized = new_test_user(self.env, login='psbt_no_access', groups='base.group_user')
        values = {'input_ids': [Command.create({'wallet_id': self.wallet.id, 'txid': 'ab' * 32, 'sats': 100000000})],
                  'output_ids': [Command.create({'address': self.destination, 'sats': 90000000})]}
        wizard = self.env['bitcoin.psbt'].with_user(author).create(values)
        wizard.action_generate()
        with self.assertRaises(AccessError):
            wizard.with_user(other).read(['psbt_binary'])
        with self.assertRaises(AccessError):
            wizard.input_ids.with_user(other).read(['txid'])
        with self.assertRaises(AccessError):
            self.env['bitcoin.psbt.input'].with_user(other).create({
                'psbt_id': wizard.id, 'wallet_id': self.wallet.id, 'txid': 'ef' * 32, 'sats': 100000000,
            })
        with self.assertRaises(AccessError):
            self.env['bitcoin.psbt'].with_user(unauthorized).create(values)

    def test_high_fee_warnings_are_advisory_and_have_exact_boundaries(self):
        wizard = self._wizard()
        for input_sats, output_sats, expected in [
            (100_000_000, 99_900_001, False),  # 99,999 sat, less than 1%
            (100_000_000, 99_900_000, True),   # absolute 100,000 sat threshold
            (100_000, 99_001, False),
            (100_000, 99_000, True),           # exactly 1% of declared inputs
        ]:
            with self.subTest(input_sats=input_sats, output_sats=output_sats):
                wizard.input_ids.sats = input_sats
                wizard.output_ids.sats = output_sats
                self.assertEqual('Large declared fee' in (wizard.review_warnings or ''), expected)
                wizard.action_generate()
                self.assertTrue(wizard.psbt_binary)

    def test_zero_fee_warning_does_not_block_generation(self):
        wizard = self._wizard()
        wizard.output_ids.sats = wizard.input_ids.sats
        self.assertIn('fee is zero', wizard.review_warnings)
        self.assertNotIn('Large declared fee', wizard.review_warnings)
        wizard.action_generate()
        self.assertTrue(wizard.psbt_binary)

    def test_dust_output_warning_boundary_and_zero_amount(self):
        wizard = self._wizard()
        for value, is_dust in [(0, True), (293, True), (294, False)]:
            with self.subTest(value=value):
                wizard.output_ids.sats = value
                self.assertEqual('dust threshold' in (wizard.review_warnings or ''), is_dust)
                wizard.action_generate()
                self.assertTrue(wizard.psbt_binary)

    def test_change_warning_and_recovery_window(self):
        wizard = self._wizard()
        self.assertIn('No explicit change', wizard.review_warnings)
        wizard.output_ids.write({
            'destination_type': 'wallet', 'wallet_id': self.wallet.id, 'branch': '1',
            'address_index': self.wallet.address_amount,
        })
        self.assertNotIn('No explicit change', wizard.review_warnings)
        self.assertIn('outside its configured address window', wizard.review_warnings)
        wizard.action_generate()
        self.assertTrue(wizard.psbt_binary)
        wizard.output_ids.address_index = self.wallet.address_amount - 1
        self.assertFalse(wizard.review_warnings)

    def test_duplicate_destination_warning_compares_scripts(self):
        wizard = self._wizard()
        wizard.output_ids.sats = 50000000
        wizard.write({'output_ids': [Command.create({
            'address': self.destination.upper(), 'sats': 50000000,
        })]})
        self.assertIn('Outputs 1 and 2 pay the same destination', wizard.review_warnings)
        wizard.action_generate()
        self.assertTrue(wizard.psbt_binary)
        wizard.output_ids[1].write({
            'destination_type': 'wallet', 'wallet_id': self.wallet.id, 'address_index': 12,
        })
        self.assertIn('same destination', wizard.review_warnings)

    def test_review_warnings_survive_incomplete_rows(self):
        wizard = self._wizard()
        wizard.input_ids.sats = -1
        wizard.output_ids.address = 'not-an-address'
        self.assertFalse(wizard.review_warnings)
        self.assertTrue(wizard.amount_error)
        with self.assertRaises(ValidationError):
            wizard.action_generate()

    def test_review_warnings_update_in_form(self):
        wizard = self._wizard()
        with Form(wizard) as form:
            self.assertNotIn('Large declared fee', form.review_warnings)
            with form.output_ids.edit(0) as line:
                line.sats = 50000000
            self.assertIn('Large declared fee', form.review_warnings)

    def test_wrong_network_destination_is_rejected(self):
        wizard = self._wizard()
        # Bitcoin Core's published regtest creator-vector destination.
        wizard.output_ids.address = 'bcrt1qmpwzkuwsqc9snjvgdt4czhjsnywa5yjdqpxskv'
        with self.assertRaisesRegex(Exception, 'expected mainnet'):
            wizard.action_generate()

    def test_op_return_text_and_hex_and_bare(self):
        wizard = self._wizard()
        wizard.write({'output_ids': [
            Command.create({'destination_type': 'op_return', 'op_return_format': 'text',
                            'op_return_data': 'hello', 'sats': 0}),
        ]})
        wizard.action_generate()
        raw = base64.b64decode(wizard.psbt_binary)
        self.assertIn(b'\x6a\x05hello', raw)

        wizard.output_ids[1].write({'op_return_format': 'hex', 'op_return_data': 'deadbeef'})
        wizard.action_generate()
        raw = base64.b64decode(wizard.psbt_binary)
        self.assertIn(b'\x6a\x04\xde\xad\xbe\xef', raw)

        wizard.output_ids[1].write({'op_return_data': ''})
        wizard.action_generate()
        raw = base64.b64decode(wizard.psbt_binary)
        self.assertIn(b'\x00' * 8 + b'\x02\x6a\x00', raw)

    def test_op_return_pushdata_boundaries(self):
        wizard = self._wizard()
        data_75 = 'a' * 75
        wizard.write({'output_ids': [
            Command.create({'destination_type': 'op_return', 'op_return_format': 'text',
                            'op_return_data': data_75, 'sats': 0}),
        ]})
        wizard.action_generate()
        raw = base64.b64decode(wizard.psbt_binary)
        self.assertIn(b'\x6a\x4b' + data_75.encode('ascii'), raw)

        data_76 = 'b' * 76
        wizard.output_ids[1].op_return_data = data_76
        wizard.action_generate()
        raw = base64.b64decode(wizard.psbt_binary)
        self.assertIn(b'\x6a\x4c\x4c' + data_76.encode('ascii'), raw)

        data_256 = 'c' * 256
        wizard.output_ids[1].op_return_data = data_256
        wizard.action_generate()
        raw = base64.b64decode(wizard.psbt_binary)
        self.assertIn(b'\x6a\x4d\x00\x01' + data_256.encode('ascii'), raw)

    def test_op_return_validation_errors(self):
        wizard = self._wizard()
        wizard.write({'output_ids': [
            Command.create({'destination_type': 'op_return', 'op_return_format': 'hex',
                            'op_return_data': 'invalid_hex', 'sats': 0}),
        ]})
        with self.assertRaises(Exception):
            wizard.action_generate()

        wizard.output_ids[1].op_return_data = 'abc'
        with self.assertRaises(Exception):
            wizard.action_generate()

        wizard.output_ids[1].write({'op_return_format': 'text', 'op_return_data': 'hällö'})
        with self.assertRaises(Exception):
            wizard.action_generate()

        wizard.output_ids[1].write({'op_return_format': 'text', 'op_return_data': 'x' * 10_001})
        with self.assertRaises(Exception):
            wizard.action_generate()

    def test_op_return_warnings_and_no_dust(self):
        wizard = self._wizard()
        wizard.output_ids.write({
            'destination_type': 'op_return', 'op_return_format': 'text',
            'op_return_data': 'note', 'sats': 0,
        })
        self.assertFalse(any('dust' in w.lower() for w in (wizard.review_warnings or '').split('\n\n')))
        wizard.action_generate()
        self.assertTrue(wizard.psbt_binary)

        wizard.output_ids.sats = 100000
        self.assertTrue(bool(wizard.review_warnings))
        wizard.action_generate()
        self.assertTrue(wizard.psbt_binary)

        wizard.output_ids.write({'sats': 0, 'op_return_data': 'x' * 81})
        self.assertTrue(bool(wizard.review_warnings))
        wizard.action_generate()
        self.assertTrue(wizard.psbt_binary)

        wizard.write({'output_ids': [
            Command.create({'destination_type': 'op_return', 'op_return_data': 'first', 'sats': 0}),
        ]})
        self.assertTrue(bool(wizard.review_warnings))
        wizard.action_generate()
        self.assertTrue(wizard.psbt_binary)

    def test_op_return_export_invalidation(self):
        wizard = self._wizard()
        wizard.output_ids.write({
            'destination_type': 'op_return', 'op_return_format': 'text',
            'op_return_data': 'test', 'sats': 0,
        })
        wizard.action_generate()
        self.assertTrue(wizard.psbt_binary)

        wizard.output_ids.op_return_data = 'test2'
        self.assertFalse(wizard.psbt_binary)
        self.assertFalse(wizard.psbt_base64)

        wizard.action_generate()
        self.assertTrue(wizard.psbt_binary)

        wizard.output_ids.op_return_format = 'hex'
        self.assertFalse(wizard.psbt_binary)
        self.assertFalse(wizard.psbt_base64)

    def test_rbf_signaling_default_and_toggle(self):
        wizard = self._wizard()
        self.assertTrue(wizard.rbf)
        wizard.action_generate()
        raw = base64.b64decode(wizard.psbt_binary)
        rbf_bytes = b'\x00' + InputSequence.RBF.to_bytes(4, 'little')
        final_bytes = b'\x00' + InputSequence.FINAL.to_bytes(4, 'little')
        self.assertIn(rbf_bytes, raw)
        self.assertNotIn(final_bytes, raw)

        wizard.rbf = False
        wizard.action_generate()
        raw = base64.b64decode(wizard.psbt_binary)
        self.assertIn(final_bytes, raw)
        self.assertNotIn(rbf_bytes, raw)

    def test_rbf_toggle_invalidates_export(self):
        wizard = self._wizard()
        wizard.action_generate()
        self.assertTrue(wizard.psbt_binary)

        wizard.rbf = False
        self.assertFalse(wizard.psbt_binary)
        self.assertFalse(wizard.psbt_base64)

        wizard.action_generate()
        self.assertTrue(wizard.psbt_binary)

        wizard.rbf = True
        self.assertFalse(wizard.psbt_binary)
        self.assertFalse(wizard.psbt_base64)

    def test_spend_missing_key_derivation_path_or_fingerprint_raises(self):
        wizard = self._wizard()
        self.key.write({'real_derivation_path': False, 'real_parent_fingerprint': self.root.fingerprint.hex()})
        with self.assertRaises(ValidationError):
            wizard.input_ids._spend()
        self.key.write({'real_derivation_path': False, 'real_parent_fingerprint': False})
        with self.assertRaises(ValidationError):
            wizard.input_ids._spend()

    def test_spend_address_matches_wallet_address_record(self):
        wizard = self._wizard(input_ids=[Command.create({
            'wallet_id': self.wallet.id, 'txid': 'ab' * 32, 'output_index': 7,
            'branch': '0', 'address_index': 0, 'sats': 123456789,
        })])
        spend = wizard.input_ids._spend()
        addr_record = self.env['bitcoin.wallet.address'].create({
            'wallet_id': self.wallet.id, 'atype': '0', 'index': 0, 'address': spend.address,
        })
        wizard.action_generate()
        self.assertEqual(wizard.input_ids.derived_address, addr_record.address)

    def test_spend_address_mismatch_raises_validation_error(self):
        wizard = self._wizard(input_ids=[Command.create({
            'wallet_id': self.wallet.id, 'txid': 'ab' * 32, 'output_index': 7,
            'branch': '0', 'address_index': 0, 'sats': 123456789,
        })])
        self.env['bitcoin.wallet.address'].create({
            'wallet_id': self.wallet.id, 'atype': '0', 'index': 0,
            'address': self.destination,
        })
        with self.assertRaises(ValidationError):
            wizard.input_ids._spend()
        with self.assertRaises(ValidationError):
            wizard.action_generate()


