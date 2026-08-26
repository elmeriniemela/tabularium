# -*- coding: utf-8 -*-

import json
import socketserver
import threading
from datetime import datetime, timedelta

from btclib.bip32 import derive

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


class _ElectrumRPCHandler(socketserver.StreamRequestHandler):
    def handle(self):
        while True:
            line = self.rfile.readline()
            if not line:
                break
            request = json.loads(line.decode('utf-8'))
            if isinstance(request, list):
                response = [self.server.dispatch(item) for item in request]
            else:
                response = self.server.dispatch(request)
            self.wfile.write(json.dumps(response).encode('utf-8') + b'\n')
            self.wfile.flush()


class _ElectrumRPCServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True

    def __init__(self, host_port, dispatch):
        self.dispatch = dispatch
        super().__init__(host_port, _ElectrumRPCHandler)


@tagged('post_install', '-at_install')
class TestBitcoinInvestmentIntegration(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.currency = cls.company.currency_id
        cls.category = cls.env['investment.category'].create({
            'name': 'Bitcoin Test Category',
            'liquid': True,
        })
        cls.portfolio = cls.env['investment.portfolio'].create({
            'name': 'Bitcoin Test Portfolio',
        })
        cls.config = cls.env['ir.config_parameter'].sudo()
        cls._root_xpub = (
            'xpub661MyMwAqRbcGFeMhhkrJL6Yj3YKQFNZQSM2BAvoMmhdjNKBh43n5v3c4YT5dFtjkirfhqQH'
            'Md22br7cHAQXAV8cZdicedZJkNweja4WWBK'
        )
        cls._seed = 1
        cls._tx_counter = 1

    def _next_seed(self):
        cls = type(self)
        cls._seed += 1
        return cls._seed

    def _next_txid(self):
        cls = type(self)
        cls._tx_counter += 1
        return f'{cls._tx_counter:064x}'

    def _new_key(self, **overrides):
        index = self._next_seed()
        values = {
            'name': f'Key {self._seed}',
            'wif': derive(self._root_xpub, str(index)),
            'witness_type': 'segwit',
            'multisig': False,
        }
        values.update(overrides)
        return self.env['bitcoin.key'].create(values)

    def _new_asset_position(self, ticker):
        asset = self.env['investment.asset'].create({
            'ticker': ticker,
            'category_id': self.category.id,
            'currency_id': self.currency.id,
            'expected_yearly_appreciation': 0.0,
            'plausible_ath_drawdown': 0.0,
        })
        initial_price = self.env['investment.asset.price'].create({
            'asset_id': asset.id,
            'time': fields.Datetime.now() - timedelta(days=1),
            'price': 1.0,
        })
        asset.last_price_id = initial_price
        position = self.env['investment.position'].create({
            'name': f'Position {ticker}',
            'asset_id': asset.id,
            'portfolio_id': self.portfolio.id,
            'company_id': self.company.id,
        })
        return asset, position

    def _new_wallet(self, *, position=None, name='Wallet'):
        wallet = self.env['bitcoin.wallet'].create({
            'name': f'{name} {self._testMethodName}',
            'address_amount': 1,
            'gap_limit': 1,
            'position_id': position.id if position else False,
        })
        key = self._new_key()
        self.env['bitcoin.wallet.key'].create({
            'wallet_id': wallet.id,
            'key_id': key.id,
            'sequence': 0,
        })
        return wallet

    def _new_tx(self):
        return self.env['bitcoin.tx'].create({'txid': self._next_txid()})

    def _new_history(self, *, wallet, tx, amount, date, position_transaction=None):
        values = {
            'wallet_id': wallet.id,
            'transaction_id': tx.id,
            'amount': amount,
            'date': date,
        }
        if position_transaction:
            values['position_transaction_id'] = position_transaction.id
        return self.env['bitcoin.wallet.history'].create(values)

    def _new_price(self, asset, time, price):
        return self.env['investment.asset.price'].create({
            'asset_id': asset.id,
            'time': time,
            'price': price,
        })

    def _start_electrum_server(self, dispatch):
        server = _ElectrumRPCServer(('127.0.0.1', 0), dispatch)
        thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.01}, daemon=True)
        thread.start()
        self.addCleanup(server.shutdown)
        self.addCleanup(server.server_close)
        self.addCleanup(thread.join, 1)
        return server, server.server_address[1]

    def _set_electrumx(self, port):
        self.config.set_param('electrumx.host', '127.0.0.1')
        self.config.set_param('electrumx.port', str(port))
        self.config.set_param('electrumx.use_ssl', '0')

    def test_sync_investments_creates_transaction_and_action(self):
        asset, position = self._new_asset_position('BTC-SYNC-CREATE')
        wallet = self._new_wallet(position=position)
        tx = self._new_tx()
        history_time = fields.Datetime.now().replace(hour=18, minute=0, second=0, microsecond=0)
        self._new_price(asset, history_time.replace(hour=12), 20000.0)
        history = self._new_history(wallet=wallet, tx=tx, amount=0.5, date=history_time)

        wallet.sync_investments()

        self.assertTrue(history.position_transaction_id)
        self.assertEqual(history.position_transaction_id.position_id, position)
        self.assertAlmostEqual(history.position_transaction_id.quantity, 0.5)
        self.assertAlmostEqual(history.position_transaction_id.payment, 10000.0)
        self.assertAlmostEqual(history.position_transaction_id.exchange_rate, 20000.0)

        action = wallet.show_investment_transactions()
        self.assertEqual(action['res_model'], 'investment.position.transaction')
        self.assertEqual(action['domain'], [('id', 'in', history.position_transaction_id.ids)])

    def test_sync_investments_limit_one_creates_latest_transaction(self):
        asset, position = self._new_asset_position('BTC-SYNC-LATEST')
        wallet = self._new_wallet(position=position)
        wallet.position_sync_limit = 1
        history_time = fields.Datetime.now().replace(hour=18, minute=0, second=0, microsecond=0)
        self._new_price(asset, history_time.replace(hour=12), 20000.0)
        histories = self.env['bitcoin.wallet.history']
        for minutes_ago in range(2):
            histories |= self._new_history(
                wallet=wallet,
                tx=self._new_tx(),
                amount=0.1,
                date=history_time - timedelta(minutes=minutes_ago),
            )

        wallet.sync_investments()

        self.assertEqual(position.transaction_ids, histories.sorted()[:1].position_transaction_id)
        self.assertFalse(histories.sorted()[1:].position_transaction_id)

    def test_sync_investments_does_not_unlink_over_lowered_limit(self):
        asset, position = self._new_asset_position('BTC-SYNC-LIMIT')
        wallet = self._new_wallet(position=position)
        history_time = fields.Datetime.now().replace(hour=18, minute=0, second=0, microsecond=0)
        self._new_price(asset, history_time.replace(hour=12), 20000.0)
        histories = self.env['bitcoin.wallet.history']
        for minutes_ago in range(3):
            histories |= self._new_history(
                wallet=wallet,
                tx=self._new_tx(),
                amount=0.1,
                date=history_time - timedelta(minutes=minutes_ago),
            )

        wallet.sync_investments()
        wallet.position_sync_limit = 1
        wallet.sync_investments()

        self.assertEqual(len(position.transaction_ids), 3)
        self.assertEqual(len(histories.position_transaction_id), 3)

    def test_sync_investments_counts_existing_position_transactions(self):
        asset, position = self._new_asset_position('BTC-SYNC-REASSIGN')
        old_wallet = self._new_wallet(position=position, name='Old wallet')
        history_time = fields.Datetime.now().replace(hour=18, minute=0, second=0, microsecond=0)
        self._new_price(asset, history_time.replace(hour=12), 20000.0)
        old_history = self._new_history(
            wallet=old_wallet,
            tx=self._new_tx(),
            amount=0.1,
            date=history_time - timedelta(minutes=2),
        )
        old_wallet.position_sync_limit = 1
        old_wallet.sync_investments()

        old_wallet.position_id = False
        new_wallet = self._new_wallet(position=position, name='New wallet')
        new_wallet.position_sync_limit = 1
        new_histories = self.env['bitcoin.wallet.history']
        for minutes_ago in range(2):
            new_histories |= self._new_history(
                wallet=new_wallet,
                tx=self._new_tx(),
                amount=0.1,
                date=history_time - timedelta(minutes=minutes_ago),
            )

        new_wallet.sync_investments()

        self.assertEqual(len(position.transaction_ids), 2)

    def test_sync_investments_zero_limit_creates_nothing(self):
        asset, position = self._new_asset_position('BTC-SYNC-ZERO')
        wallet = self._new_wallet(position=position)
        wallet.position_sync_limit = 0
        history_time = fields.Datetime.now().replace(hour=18, minute=0, second=0, microsecond=0)
        self._new_price(asset, history_time.replace(hour=12), 20000.0)
        histories = self.env['bitcoin.wallet.history']
        for minutes_ago in range(2):
            histories |= self._new_history(
                wallet=wallet,
                tx=self._new_tx(),
                amount=0.1,
                date=history_time - timedelta(minutes=minutes_ago),
            )

        wallet.sync_investments()

        self.assertFalse(position.transaction_ids)
        self.assertFalse(histories.position_transaction_id)

    def test_sync_investments_skips_unlinked_wallet_and_existing_line(self):
        asset, position = self._new_asset_position('BTC-SYNC-SKIP')
        wallet_with_position = self._new_wallet(position=position, name='Linked')
        wallet_without_position = self._new_wallet(name='No Position')
        history_time = fields.Datetime.now().replace(hour=16, minute=0, second=0, microsecond=0)
        self._new_price(asset, history_time.replace(hour=10), 100.0)

        linked_tx = self.env['investment.position.transaction'].create({
            'position_id': position.id,
            'time': history_time,
            'payment': 10.0,
            'quantity': 0.1,
            'exchange_rate': 100.0,
            'description': 'Keep me',
        })
        history_linked = self._new_history(
            wallet=wallet_with_position,
            tx=self._new_tx(),
            amount=0.1,
            date=history_time,
            position_transaction=linked_tx,
        )
        history_unlinked = self._new_history(
            wallet=wallet_without_position,
            tx=self._new_tx(),
            amount=0.2,
            date=history_time,
        )

        (wallet_with_position + wallet_without_position).sync_investments()

        self.assertEqual(history_linked.position_transaction_id, linked_tx)
        self.assertEqual(linked_tx.description, 'Keep me')
        self.assertFalse(history_unlinked.position_transaction_id)

    def test_sync_investments_transfer_between_wallets(self):
        asset, position_a = self._new_asset_position('BTC-SYNC-TRANSFER')
        position_b = self.env['investment.position'].create({
            'name': 'Position BTC-SYNC-TRANSFER-B',
            'asset_id': asset.id,
            'portfolio_id': self.portfolio.id,
            'company_id': self.company.id,
        })
        wallet_a = self._new_wallet(position=position_a, name='Wallet A')
        wallet_b = self._new_wallet(position=position_b, name='Wallet B')
        tx = self._new_tx()
        history_time = fields.Datetime.now().replace(hour=14, minute=0, second=0, microsecond=0)
        self._new_price(asset, history_time.replace(hour=12), 30000.0)

        position_tx = self.env['investment.position.transaction'].create({
            'position_id': position_a.id,
            'time': history_time,
            'payment': 3000.0,
            'quantity': 0.1,
            'exchange_rate': 30000.0,
            'description': 'Original',
        })
        self._new_history(
            wallet=wallet_a,
            tx=tx,
            amount=-0.3,
            date=history_time,
            position_transaction=position_tx,
        )
        history_b = self._new_history(
            wallet=wallet_b,
            tx=tx,
            amount=0.3,
            date=history_time,
        )

        wallet_b.sync_investments()

        self.assertEqual(history_b.position_transaction_id, position_tx)
        position_tx.invalidate_recordset(['quantity', 'payment', 'description'])
        self.assertAlmostEqual(position_tx.quantity, 0.0)
        self.assertAlmostEqual(position_tx.payment, 0.0)
        self.assertEqual(position_tx.description, 'Transfer between wallets')

    def test_sync_investments_requires_matching_daily_price(self):
        asset, position = self._new_asset_position('BTC-SYNC-PRICE')
        wallet = self._new_wallet(position=position)
        history_time = datetime(2025, 1, 10, 15, 0, 0)
        self._new_price(asset, history_time - timedelta(days=1), 12345.0)
        self._new_history(
            wallet=wallet,
            tx=self._new_tx(),
            amount=0.1,
            date=history_time,
        )

        with self.assertRaises(UserError):
            wallet.sync_investments()

    def test_fetch_bitcoin_transactions_refreshes_wallet_and_count(self):
        asset, position = self._new_asset_position('BTC-FETCH-REFRESH')
        wallet = self._new_wallet(position=position)
        history_time = fields.Datetime.now().replace(hour=17, minute=0, second=0, microsecond=0)
        self._new_price(asset, history_time.replace(hour=11), 25000.0)
        history = self._new_history(
            wallet=wallet,
            tx=self._new_tx(),
            amount=0.2,
            date=history_time,
        )

        def dispatch(request):
            if request['method'] == 'blockchain.scripthash.subscribe':
                return {'id': request['id'], 'result': None}
            raise AssertionError('Unexpected method %s' % request['method']) # pragma: no cover

        _, port = self._start_electrum_server(dispatch)
        self._set_electrumx(port)

        position.fetch_bitcoin_transactions()

        self.assertTrue(wallet.address_ids)
        self.assertTrue(history.position_transaction_id)
        position.invalidate_recordset(['wallet_count'])
        self.assertEqual(position.wallet_count, 1)
