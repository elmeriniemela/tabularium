# -*- coding: utf-8 -*-

import datetime
import json
from unittest.mock import patch

from tinyrpc.protocols.jsonrpc import JSONRPCError, JSONRPCErrorResponse

from odoo import Command
from odoo.exceptions import UserError
from odoo.orm.domains import DomainCondition
from odoo.tests import TransactionCase, tagged

from odoo.addons.bitcoin_browser.models import generic as generic_model


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
            'asm': 'OP_DUP OP_HASH160',
            'type': 'pubkeyhash',
        }
        if include_address:
            script_pub_key['address'] = f'addr-{txid}'
        rawtx = {
            'in_active_chain': in_active_chain,
            'txid': txid,
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
                    'sequence': 1,
                    'vout_tx_id': False,
                    'vout': False,
                    'coinbase': '6162',
                })],
                'vout_ids': [Command.create({
                    'n': 0,
                    'value': 0.5,
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
        self.assertFalse(vals['blocktime'])
        self.assertEqual(vals['fee'], 0.0)
        self.assertFalse(vals['vout_ids'][0][2]['address'])

        tx_with_block = self.Tx.create({'txid': 'tx-with-block', 'block_id': fetched.block_id.id})
        with self._patch_proxy(FakeProxy(fail_getraw=True)):
            tx_with_block.refresh()

        with self._patch_proxy(FakeProxy(fail_getraw=True)):
            tx_error = self.Tx.create({'txid': 'tx-error'})
            with self.assertRaises(UserError):
                tx_error.refresh()

    def test_input_output_create_and_link_compute(self):
        origin = self.Tx.create({'txid': 'origin-tx'})
        spender = self.Tx.create({'txid': 'spender-tx'})

        output = self.TxOut.create({
            'tx_id': origin.id,
            'n': 0,
            'type': 'pubkeyhash',
            'address': 'addr-1',
            'asm': 'asm-1',
            'value': 1.0,
        })
        output_updated = self.TxOut.create({
            'tx_id': origin.id,
            'n': 0,
            'type': 'nulldata',
            'address': 'addr-2',
            'asm': 'asm-2',
            'value': 2.0,
        })
        self.assertEqual(output.id, output_updated.id)
        self.assertEqual(self.TxOut.search_count([('tx_id', '=', origin.id), ('n', '=', 0)]), 1)
        self.assertEqual(output.type, 'nulldata')

        tx_input = self.TxIn.create({
            'tx_id': spender.id,
            'sequence': 1,
            'vout_tx_id': origin.txid,
            'vout': 0,
            'coinbase': False,
        })
        self.assertEqual(tx_input.vout_tx_id, origin)

        tx_input_updated = self.TxIn.create({
            'tx_id': spender.id,
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
            'sequence': 3,
            'vout_tx_id': False,
            'vout': False,
            'coinbase': '616263',
        })
        coinbase_updated = self.TxIn.create({
            'tx_id': spender.id,
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
