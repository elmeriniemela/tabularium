# -*- coding: utf-8 -*-

import datetime
import json
from types import SimpleNamespace
from unittest.mock import patch

from tinyrpc.protocols.jsonrpc import JSONRPCError, JSONRPCErrorResponse

from odoo import Command
from odoo.exceptions import UserError
from odoo.orm.domains import DomainCondition
from odoo.tests import HttpCase, TransactionCase, tagged

from odoo.addons.bitcoin_browser.models import generic as generic_model
from odoo.addons.bitcoin_browser.models import tx as tx_model


def _now():
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None, microsecond=0)


def _rpc_error(*, code, message):
    response = JSONRPCErrorResponse()
    response._jsonrpc_error_code = code
    response.error = message
    return JSONRPCError(response)


class FakeProxy:

    def __init__(self, *, blocks=None, txs=None, bestblockhash=None, fail_getblock=False, fail_getraw=False):
        self.blocks = blocks or {}
        self.txs = txs or {}
        self.bestblockhash = bestblockhash
        self.fail_getblock = fail_getblock
        self.fail_getraw = fail_getraw

    def getblockchaininfo(self):
        return {'bestblockhash': self.bestblockhash}

    def getblock(self, block_hash, verbosity):
        if self.fail_getblock:
            raise _rpc_error(code=-1, message='boom getblock')
        data = dict(self.blocks[block_hash])
        if verbosity == 1 and data.get('tx') and isinstance(data['tx'][0], dict):
            data['tx'] = [tx['txid'] for tx in data['tx']]
        return data

    def getrawtransaction(self, txid, verbose):
        del verbose
        if self.fail_getraw:
            raise _rpc_error(code=-2, message='boom getrawtransaction')
        return dict(self.txs[txid])


@tagged('post_install', '-at_install')
class TestBitcoinBrowser(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Block = cls.env['bitcoin.block']
        cls.Tx = cls.env['bitcoin.tx']
        cls.TxIn = cls.env['bitcoin.tx.in']
        cls.TxOut = cls.env['bitcoin.tx.out']
        cls.Config = cls.env['ir.config_parameter'].sudo()

    def _rawtx(
        self,
        txid,
        *,
        blockhash=False,
        blocktime=None,
        fee=0.01,
        include_address=True,
        in_active_chain=True,
    ):
        script_pub_key = {
            'hex': '76a9144bfbaf6afb76cc5771bc6404810d1cc041a6933988ac',
            'asm': 'OP_DUP OP_HASH160',
            'type': 'pubkeyhash',
        }
        if include_address:
            script_pub_key['address'] = f'addr-{txid}'
        rawtx = {
            'in_active_chain': in_active_chain,
            'txid': txid,
            'hex': (
                '02000000013f7cebd65c27431a90bba7f796914fe8cc2ddfc3f2cbd6f7e5f2fc854534da'
                '95000000006b483045022100de1ac3bcdfb0332207c4a91f3832bd2c2915840165f876ab'
                '47c5f8996b971c3602201c6c053d750fadde599e6f5c4e1963df0f01fc0d97815e8157e3'
                'd59fe09ca30d012103699b464d1d8bc9e47d4fb1cdaa89a1c5783d68363c4dbc4b524ed3'
                'd857148617feffffff02836d3c01000000001976a914fc25d6d5c94003bf5b0c7b640a24'
                '8e2c637fcfb088ac7ada8202000000001976a914fbed3d9b11183209a57999d54d59f67c'
                '019e756c88ac6acb0700'
            ),
            'hash': f'hash-{txid}',
            'version': 2,
            'size': 200,
            'vsize': 140,
            'weight': 560,
            'locktime': 0,
            'vin': [{'sequence': 1, 'txid': f'prev-{txid}', 'vout': 0}],
            'vout': [{'n': 0, 'value': 1.23, 'scriptPubKey': script_pub_key}],
        }
        if blockhash:
            rawtx['blockhash'] = blockhash
        if blocktime is not None:
            rawtx['blocktime'] = blocktime
        if fee is not None:
            rawtx['fee'] = fee
        return rawtx

    def _block(self, block_hash, *, height, previousblockhash=False, tx=None, mediantime=None):
        tx = tx or []
        if mediantime is None:
            mediantime = _now()
        block_ts = int(mediantime.timestamp())
        return {
            'confirmations': 1,
            'height': height,
            'version': 4,
            'merkleroot': f'merkle-{block_hash}',
            'time': block_ts,
            'mediantime': block_ts,
            'nonce': 123,
            'bits': '1d00ffff',
            'difficulty': 1.0,
            'chainwork': f'cw-{block_hash}',
            'nTx': len(tx),
            'previousblockhash': previousblockhash,
            'size': 1000,
            'strippedsize': 900,
            'weight': 3900,
            'tx': tx,
        }

    def _patch_proxy(self, proxy):
        return patch.object(generic_model.ConfigParam, 'bitcoind_proxy', autospec=True, return_value=proxy)

    def test_generic_protocol_and_config_proxy(self):
        protocol = generic_model.BitcoinJSONRPCProtocol()

        request_ok = protocol.create_request('method.ok')
        ok = protocol.parse_reply(json.dumps({
            'id': request_ok.unique_id,
            'result': 7,
            'error': None,
        }).encode())
        self.assertEqual(ok.result, 7)

        request_error = protocol.create_request('method.error')
        err = protocol.parse_reply(json.dumps({
            'id': request_error.unique_id,
            'result': None,
            'error': {'code': -100, 'message': 'rpc failed'},
        }).encode())
        self.assertEqual(err.error, 'rpc failed')

        self.Config.set_param('bitcoind.url', 'http://127.0.0.1:8332')
        self.Config.set_param('bitcoind.user', 'user')
        self.Config.set_param('bitcoind.pw', 'pw')
        self.assertTrue(self.Config.bitcoind_proxy())

    def test_block_create_search_fetch_compute_and_errors(self):
        existing = self.Block.create({'hash': 'block-existing', 'height': 1, 'n_tx': 2})
        updated = self.Block.create({'hash': 'block-existing', 'height': 5, 'n_tx': 2})
        self.assertEqual(existing.id, updated.id)
        self.assertEqual(self.Block.search_count([('hash', '=', 'block-existing')]), 1)

        self.Tx.create({'txid': 'count-1', 'block_id': existing.id})
        self.Tx.create({'txid': 'count-2', 'block_id': existing.id})
        existing._compute_computed_n_tx()
        self.assertEqual(existing.computed_n_tx, 2)
        self.assertTrue(existing.all_tx_fetched)
        existing.n_tx = 3
        existing._compute_computed_n_tx()
        self.assertFalse(existing.all_tx_fetched)

        self.assertFalse(
            self.Block.with_context(disable_auto_populate=True).search_fetch(
                [('hash', '=', 'block-auto')], ['hash']
            )
        )
        self.assertFalse(self.Block.search_fetch([('height', '=', 99999999)], ['hash']))

        now = _now()
        rawtx = self._rawtx('tx-block-auto', blockhash='block-auto', blocktime=int(now.timestamp()))
        proxy = FakeProxy(
            blocks={
                'block-auto': self._block(
                    'block-auto',
                    height=10,
                    previousblockhash='block-prev',
                    tx=[rawtx],
                    mediantime=now,
                ),
                'block-genesis': self._block(
                    'block-genesis',
                    height=0,
                    previousblockhash='will-be-ignored',
                    tx=[rawtx],
                ),
            },
            txs={rawtx['txid']: rawtx},
        )
        with self._patch_proxy(proxy):
            block = self.Block.search_fetch([('hash', '=', 'block-auto')], ['hash'])
            self.assertTrue(block)
            self.assertEqual(block.n_tx, 1)
            self.assertEqual(block.tx_ids.txid, rawtx['txid'])
            self.assertEqual(block.tx_ids.block_id, block)

            existing_search = self.Block.search_fetch([('hash', '=', block.hash)], ['hash'])
            self.assertEqual(existing_search, block)
            domain_search = self.Block.search_fetch(DomainCondition('hash', '=', block.hash), ['hash'])
            self.assertEqual(domain_search, block)

            genesis = self.Block.create({'hash': 'block-genesis'})
            vals = genesis.fetchblock(tx=False)
            self.assertFalse(vals['previousblockhash'])
            self.assertNotIn('tx_ids', vals)

        with self._patch_proxy(FakeProxy(fail_getblock=True)):
            with self.assertRaises(UserError):
                existing.fetchblock(tx=True)

    def test_block_web_read_tx_ids(self):
        block = self.Block.create({'hash': 'block-web-read'})
        tx = self.Tx.create({'txid': 'tx-web-read', 'block_id': block.id})
        self.env.invalidate_all()

        [values] = self.Block.browse(block.id).web_read({
            'hash': {},
            'tx_ids': {'fields': {'txid': {}}},
        })

        self.assertEqual(values['tx_ids'][0]['id'], tx.id)

    def test_block_refresh_and_cron_fetch(self):
        now = _now()
        old_time = now - datetime.timedelta(hours=3)

        tx_old = self._rawtx('tx-old', blockhash='cron-1', blocktime=int(old_time.timestamp()))
        proxy = FakeProxy(
            bestblockhash='cron-3',
            blocks={
                'cron-1': self._block('cron-1', height=1, previousblockhash='cron-0', tx=[tx_old], mediantime=old_time),
            },
            txs={tx_old['txid']: tx_old},
        )

        block_1 = self.Block.create({
            'hash': 'cron-1',
            'height': 1,
            'previousblockhash': 'cron-0',
        })
        block_2 = self.Block.create({
            'hash': 'cron-2',
            'height': 2,
            'previousblockhash': 'cron-1',
            'mediantime': now - datetime.timedelta(minutes=30),
        })
        self.Block.create({
            'hash': 'cron-3',
            'height': 3,
            'previousblockhash': 'cron-2',
            'mediantime': now - datetime.timedelta(minutes=10),
        })

        self.Config.set_param('bitoind.history.hours', '1')
        with self._patch_proxy(proxy):
            self.Block.cron_fetch()

        self.assertEqual(block_2.confirmations, 2)
        self.assertEqual(block_1.confirmations, 3)
        self.assertTrue(block_1.mediantime)

    def test_tx_create_search_fetch_refresh_rawtx_and_errors(self):
        tx_existing = self.Tx.create({'txid': 'tx-existing'})
        created = self.Tx.create([
            {
                'txid': 'tx-existing',
                'vin_ids': [Command.create({
                    'n': 0,
                    'sequence': 11,
                    'vout_tx_id': 'tx-linked',
                    'vout': 0,
                    'coinbase': False,
                })],
            },
            {
                'txid': 'tx-linked',
                'hash': 'hash-tx-linked',
                'version': 2,
                'size': 100,
                'vsize': 90,
                'weight': 360,
                'locktime': 0,
                'vin_ids': [Command.create({
                    'n': 0,
                    'sequence': 1,
                    'vout_tx_id': False,
                    'vout': False,
                    'coinbase': '6162',
                })],
                'vout_ids': [Command.create({
                    'n': 0,
                    'value': 0.5,
                    'script_pub_key_hex': '76a9144bfbaf6afb76cc5771bc6404810d1cc041a6933988ac',
                    'address': 'addr-linked',
                    'asm': 'asm-linked',
                    'type': 'pubkeyhash',
                })],
            },
        ])
        self.assertEqual(self.Tx.search_count([('txid', '=', 'tx-existing')]), 1)
        self.assertEqual(self.Tx.search_count([('txid', '=', 'tx-linked')]), 1)
        self.assertIn(tx_existing, created)

        self.assertFalse(
            self.Tx.with_context(disable_auto_populate=True).search_fetch(
                [('txid', '=', 'tx-search')], ['txid']
            )
        )
        self.assertFalse(self.Tx.search_fetch([('version', '=', 123456)], ['txid']))

        now = _now()
        raw_search = self._rawtx('tx-search', blockhash='block-for-search', blocktime=int(now.timestamp()))
        proxy = FakeProxy(txs={'tx-search': raw_search})
        with self._patch_proxy(proxy):
            fetched = self.Tx.search_fetch([('txid', '=', 'tx-search')], ['txid'])
            self.assertTrue(fetched.block_id)
            self.assertEqual(fetched.block_id.hash, 'block-for-search')
            self.assertEqual(fetched.txid, 'tx-search')
            self.assertEqual(len(fetched.vout_ids), 1)

            existing = self.Tx.create({'txid': 'tx-needs-refresh'})
            proxy.txs['tx-needs-refresh'] = self._rawtx(
                'tx-needs-refresh',
                blockhash='block-needs-refresh',
                blocktime=int(now.timestamp()),
            )
            refreshed = self.Tx.search_fetch([('txid', '=', 'tx-needs-refresh')], ['txid'])
            self.assertEqual(refreshed.block_id.hash, 'block-needs-refresh')

        raw_no_blocktime = self._rawtx('tx-no-blocktime', blocktime=None, fee=None, include_address=False)
        vals = self.Tx.rawtx_to_vals(raw_no_blocktime)
        self.assertEqual(vals['hex'], raw_no_blocktime['hex'])
        self.assertEqual(vals['vin_ids'][0][2]['n'], 0)
        self.assertEqual(vals['vout_ids'][0][2]['script_pub_key_hex'], raw_no_blocktime['vout'][0]['scriptPubKey']['hex'])
        self.assertFalse(vals['blocktime'])
        self.assertEqual(vals['fee'], 0.0)
        self.assertFalse(vals['vout_ids'][0][2]['address'])

        tx_with_block = self.Tx.create({'txid': 'tx-with-block', 'block_id': fetched.block_id.id})
        with self._patch_proxy(FakeProxy(fail_getraw=True)):
            tx_with_block.refresh()
        self.assertFalse(tx_with_block.hex)

        raw_with_block = self._rawtx(
            'tx-with-block',
            blockhash=fetched.block_id.hash,
            blocktime=int(now.timestamp()),
        )
        # A forced refresh also refreshes the inputs' source transactions, so the
        # tx referenced by the vin ('prev-tx-with-block') must be available too.
        raw_prev = self._rawtx(
            'prev-tx-with-block',
            blockhash=fetched.block_id.hash,
            blocktime=int(now.timestamp()),
        )
        with self._patch_proxy(FakeProxy(txs={
            'tx-with-block': raw_with_block,
            'prev-tx-with-block': raw_prev,
        })):
            tx_with_block.with_context(force_tx_refresh=True).refresh()
        self.assertEqual(tx_with_block.hex, raw_with_block['hex'])
        self.assertEqual(tx_with_block.vin_ids.n, 0)
        self.assertEqual(tx_with_block.vout_ids.script_pub_key_hex, raw_with_block['vout'][0]['scriptPubKey']['hex'])

        with self._patch_proxy(FakeProxy(fail_getraw=True)):
            tx_error = self.Tx.create({'txid': 'tx-error'})
            with self.assertRaises(UserError):
                tx_error.refresh()

    def test_tx_debug_script_builds_bitoplens_inputs_in_vin_order(self):
        script_0 = '51'
        script_1 = '52'
        prev_0 = self.Tx.create({'txid': 'debug-prev-0'})
        prev_1 = self.Tx.create({'txid': 'debug-prev-1'})
        self.TxOut.create({
            'tx_id': prev_0.id,
            'n': 0,
            'type': 'pubkey',
            'address': 'debug-addr-0',
            'asm': 'OP_1',
            'script_pub_key_hex': script_0,
            'value': 0.00000011,
        })
        self.TxOut.create({
            'tx_id': prev_1.id,
            'n': 0,
            'type': 'pubkey',
            'address': 'debug-addr-1',
            'asm': 'OP_2',
            'script_pub_key_hex': script_1,
            'value': 0.00000022,
        })
        tx = self.Tx.create({
            'txid': 'debug-spend',
            'hex': '0a0b',
            'vin_ids': [
                Command.create({
                    'n': 1,
                    'sequence': 1,
                    'vout_tx_id': prev_1.id,
                    'vout': 0,
                    'coinbase': False,
                }),
                Command.create({
                    'n': 0,
                    'sequence': 99,
                    'vout_tx_id': prev_0.id,
                    'vout': 0,
                    'coinbase': False,
                }),
            ],
        })

        calls = {
            'runs': [],
            'scripts': [],
            'outputs': [],
        }

        class FakeTransaction:

            def __init__(self, raw):
                self.raw = raw
                self.vin = [object(), object()]

            @classmethod
            def parse(cls, raw):
                calls['transaction'] = cls(raw)
                return calls['transaction']

        class FakeTxOut:

            def __init__(self, value, script_pubkey):
                self.value = value
                self.script_pubkey = script_pubkey
                calls['scripts'].append(script_pubkey)
                calls['outputs'].append(self)

        class FakeTrace:
            valid = True
            error_name = 'OK'
            runs = []

        def fake_run(script_pubkey, *, tx, input_index, spent_outputs, flags):
            del flags
            calls['runs'].append((script_pubkey, tx, input_index))
            calls['spent_outputs'] = spent_outputs
            return FakeTrace()

        fake_bl = SimpleNamespace(
            Transaction=FakeTransaction,
            TxOut=FakeTxOut,
            run=fake_run,
        )

        with patch.object(tx_model, 'bl', fake_bl):
            tx._compute_visualized_script()

        self.assertEqual(calls['transaction'].raw, bytes.fromhex(tx.hex))
        self.assertEqual(calls['scripts'], [bytes.fromhex(script_0), bytes.fromhex(script_1)])
        self.assertEqual([output.value for output in calls['outputs']], [11, 22])
        self.assertEqual(calls['spent_outputs'], calls['outputs'])
        self.assertEqual([run[0] for run in calls['runs']], [bytes.fromhex(script_0), bytes.fromhex(script_1)])
        self.assertEqual([run[1] for run in calls['runs']], [calls['transaction'], calls['transaction']])
        self.assertEqual([run[2] for run in calls['runs']], [0, 1])
        self.assertTrue(tx.is_visualized)
        self.assertIn('OK', tx.visualized_script)

    def test_tx_visualized_script_guard_states(self):
        no_hex = self.Tx.create({'txid': 'visual-no-hex'})
        no_hex._compute_visualized_script()
        self.assertFalse(no_hex.is_visualized)

        coinbase = self.Tx.create({
            'txid': 'visual-coinbase',
            'hex': '00',
            'vin_ids': [Command.create({
                'n': 0,
                'sequence': 1,
                'vout_tx_id': False,
                'vout': False,
                'coinbase': '636f696e62617365',
            })],
        })
        coinbase._compute_visualized_script()
        self.assertFalse(coinbase.is_visualized)

        parse_error = self.Tx.create({
            'txid': 'visual-parse-error',
            'hex': '00',
            'vin_ids': [Command.create({
                'n': 0,
                'sequence': 1,
                'vout_tx_id': False,
                'vout': False,
                'coinbase': False,
            })],
        })
        parse_error._compute_visualized_script()
        self.assertFalse(parse_error.is_visualized)
        self.assertIn('Unable to parse transaction hex', parse_error.visualized_script)

        input_mismatch = self.Tx.create({
            'txid': 'visual-input-mismatch',
            'hex': '00',
            'vin_ids': [Command.create({
                'n': 0,
                'sequence': 1,
                'vout_tx_id': False,
                'vout': False,
                'coinbase': False,
            })],
        })
        fake_transaction = SimpleNamespace(parse=lambda raw: SimpleNamespace(vin=[object(), object()]))
        with patch.object(tx_model.bl, 'Transaction', fake_transaction):
            input_mismatch._compute_visualized_script()
        self.assertFalse(input_mismatch.is_visualized)
        self.assertIn(
            "Stored input data does not match the raw transaction (1 stored, 2 serialized).",
            input_mismatch.visualized_script,
        )

    def test_debug_trace_html_renders_execution_details(self):
        prev = self.Tx.create({'txid': 'trace-prev'})
        self.TxOut.create({
            'tx_id': prev.id,
            'n': 0,
            'type': 'pubkey',
            'address': 'trace-addr',
            'asm': 'OP_1',
            'script_pub_key_hex': '51',
            'value': 0.00000001,
        })
        tx = self.Tx.create({
            'txid': 'trace-spend',
            'hex': '00',
            'vin_ids': [Command.create({
                'n': 0,
                'sequence': 1,
                'vout_tx_id': prev.id,
                'vout': 0,
                'coinbase': False,
            })],
        })
        run = SimpleNamespace(
            role='scriptPubKey',
            sig_version=0,
            script=b'',
            script_type='pubkeyhash',
            initial_stack=(b'', b'\x01', b'\x01', b'\xcc' * 17),
            steps=[
                SimpleNamespace(
                    opcode=81,
                    opcode_name='OP_1',
                    description='description-81',
                    script_offset=0,
                    executed=True,
                    stack=(b'\x01', b'\xaa' * 17),
                ),
                SimpleNamespace(
                    opcode=82,
                    opcode_name='OP_2',
                    description='description-82',
                    script_offset=1,
                    executed=False,
                    stack=(),
                ),
            ],
            final_stack=(b'', b'\xbb' * 17),
            error=0,
        )
        empty_run = SimpleNamespace(
            role='scriptSig',
            sig_version=0,
            script=b'\x51',
            script_type=False,
            initial_stack=(),
            steps=[],
            final_stack=(),
            error=0,
        )
        trace = SimpleNamespace(
            valid=False,
            error=0,
            error_name='TRACE_FAIL',
            runs=[run, empty_run],
        )

        fake_bl = SimpleNamespace(
            Transaction=SimpleNamespace(parse=lambda raw: SimpleNamespace(raw=raw, vin=[object()])),
            TxOut=lambda value, script_pubkey: SimpleNamespace(value=value, script_pubkey=script_pubkey),
            run=lambda script_pubkey, *, tx, input_index, spent_outputs, flags: trace,
            ScriptError=lambda error: SimpleNamespace(name='EXEC_OK'),
            SigVersion=lambda sig_version: SimpleNamespace(name='BASE'),
        )

        with patch.object(tx_model, 'bl', fake_bl):
            tx._compute_visualized_script()

        html = tx.visualized_script
        self.assertIn('TRACE_FAIL', html)
        self.assertIn('scriptPubKey', html)
        self.assertIn('OP_1', html)
        self.assertIn('OP_2', html)
        self.assertIn('stack (before)', html)
        self.assertNotIn('stack (after)', html)
        self.assertIn('cccccccccccccccccccccccccccccccc', html)
        self.assertIn('aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', html)
        self.assertIn('bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb', html)
        self.assertIn('(17 bytes)', html)
        self.assertIn('opacity:.5', html)

    def test_input_output_create_and_link_compute(self):
        origin = self.Tx.create({'txid': 'origin-tx'})
        spender = self.Tx.create({'txid': 'spender-tx'})

        output = self.TxOut.create({
            'tx_id': origin.id,
            'n': 0,
            'type': 'pubkeyhash',
            'address': 'addr-1',
            'asm': 'asm-1',
            'script_pub_key_hex': '76a9144bfbaf6afb76cc5771bc6404810d1cc041a6933988ac',
            'value': 1.0,
        })
        output_updated = self.TxOut.create({
            'tx_id': origin.id,
            'n': 0,
            'type': 'nulldata',
            'address': 'addr-2',
            'asm': 'asm-2',
            'script_pub_key_hex': '6a',
            'value': 2.0,
        })
        self.assertEqual(output.id, output_updated.id)
        self.assertEqual(self.TxOut.search_count([('tx_id', '=', origin.id), ('n', '=', 0)]), 1)
        self.assertEqual(output.type, 'nulldata')

        tx_input = self.TxIn.create({
            'tx_id': spender.id,
            'n': 0,
            'sequence': 1,
            'vout_tx_id': origin.txid,
            'vout': 0,
            'coinbase': False,
        })
        self.assertEqual(tx_input.vout_tx_id, origin)

        tx_input_updated = self.TxIn.create({
            'tx_id': spender.id,
            'n': 0,
            'sequence': 2,
            'vout_tx_id': origin.id,
            'vout': 0,
            'coinbase': False,
        })
        self.assertEqual(tx_input.id, tx_input_updated.id)
        self.assertEqual(self.TxIn.search_count([('vout_tx_id', '=', origin.id), ('vout', '=', 0)]), 1)
        self.assertEqual(tx_input.sequence, 2)

        coinbase = self.TxIn.create({
            'tx_id': spender.id,
            'n': 1,
            'sequence': 3,
            'vout_tx_id': False,
            'vout': False,
            'coinbase': '616263',
        })
        coinbase_updated = self.TxIn.create({
            'tx_id': spender.id,
            'n': 1,
            'sequence': 4,
            'vout_tx_id': False,
            'vout': False,
            'coinbase': '616263',
        })
        self.assertEqual(coinbase.id, coinbase_updated.id)
        self.assertEqual(coinbase.coinbase_ascii, 'abc')
        self.assertFalse(tx_input.coinbase_ascii)

        tx_input._compute_spent_output_id()
        output._compute_spent_input_id()
        self.assertEqual(tx_input.spent_output_id, output)
        self.assertEqual(output.spent_input_id, tx_input)


@tagged('post_install', '-at_install')
class TestBitcoinBrowserController(HttpCase):

    def _rawtx(self, txid, vin):
        return {
            'txid': txid,
            'hex': '00',
            'hash': f'hash-{txid}',
            'version': 2,
            'size': 1,
            'vsize': 1,
            'weight': 4,
            'locktime': 0,
            'vin': vin,
            'vout': [{
                'n': 0,
                'value': 1.0,
                'scriptPubKey': {
                    'hex': '51',
                    'asm': 'OP_TRUE',
                    'type': 'nonstandard',
                },
            }],
        }

    def test_visualized_script_route_renders_after_refresh(self):
        self.env['bitcoin.tx'].create({'txid': 'ctrl-refresh'})
        proxy = FakeProxy(txs={
            'ctrl-refresh': self._rawtx('ctrl-refresh', [{
                'sequence': 1,
                'txid': 'ctrl-prev-refresh',
                'vout': 0,
            }]),
            'ctrl-prev-refresh': self._rawtx('ctrl-prev-refresh', [{
                'sequence': 1,
                'coinbase': '6374726c2d707265762d72656672657368',
            }]),
        })

        class FakeTransaction:

            def __init__(self, raw):
                self.raw = raw
                self.vin = [object()]

            @classmethod
            def parse(cls, raw):
                return cls(raw)

        class FakeTxOut:

            def __init__(self, value, script_pubkey):
                self.value = value
                self.script_pubkey = script_pubkey

        class FakeTrace:
            valid = True
            error_name = 'CACHE_REFRESH_SENTINEL'
            runs = []

        fake_bl = SimpleNamespace(
            Transaction=FakeTransaction,
            TxOut=FakeTxOut,
            run=lambda script_pubkey, *, tx, input_index, spent_outputs, flags: FakeTrace(),
        )

        with self._patch_proxy(proxy), patch.object(tx_model, 'bl', fake_bl):
            response = self.url_open('/bitcoin/tx/ctrl-refresh')

        self.assertEqual(response.status_code, 200)
        self.assertIn('text/html', response.headers['Content-Type'])
        self.assertIn('CACHE_REFRESH_SENTINEL', response.text)

    def _patch_proxy(self, proxy):
        return patch.object(generic_model.ConfigParam, 'bitcoind_proxy', autospec=True, return_value=proxy)
