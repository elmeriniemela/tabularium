# -*- coding: utf-8 -*-

from odoo.tests import tagged
from .common import InvestmentTestCommon
from datetime import datetime, timedelta


@tagged('post_install', '-at_install')
class TestRealized(InvestmentTestCommon):

    def test_fifo_single_buy_single_sell(self):
        """Simple 1:1 FIFO matching"""
        pos = self.env['investment.position'].create({
            'name': 'FIFO Simple',
            'asset_id': self.asset.id,
            'portfolio_id': self.portfolio.id,
            'company_id': self.company.id,
        })
        now = datetime.now()
        self.env['investment.position.transaction'].create({
            'position_id': pos.id,
            'quantity': 10.0,
            'exchange_rate': 50.0,
            'payment': 500.0,
            'time': now - timedelta(days=20),
        })
        self.env['investment.position.transaction'].create({
            'position_id': pos.id,
            'quantity': -10.0,
            'exchange_rate': 60.0,
            'payment': 600.0,
            'time': now - timedelta(days=10),
        })
        # quantity is 0, so no simulated sell should exist
        self.assertAlmostEqual(pos.quantity, 0.0)
        realized = pos.realized_ids.filtered(lambda r: not r.simulated)
        self.assertEqual(len(realized), 1)
        self.assertAlmostEqual(realized.quantity, 10.0)

    def test_fifo_multiple_buys_one_sell(self):
        """Sell matched against multiple buys in FIFO order"""
        pos = self.env['investment.position'].create({
            'name': 'FIFO Multi Buy',
            'asset_id': self.asset.id,
            'portfolio_id': self.portfolio.id,
            'company_id': self.company.id,
        })
        now = datetime.now()
        self.env['investment.position.transaction'].create({
            'position_id': pos.id,
            'quantity': 5.0,
            'exchange_rate': 50.0,
            'payment': 250.0,
            'time': now - timedelta(days=30),
        })
        self.env['investment.position.transaction'].create({
            'position_id': pos.id,
            'quantity': 5.0,
            'exchange_rate': 60.0,
            'payment': 300.0,
            'time': now - timedelta(days=20),
        })
        self.env['investment.position.transaction'].create({
            'position_id': pos.id,
            'quantity': -10.0,
            'exchange_rate': 70.0,
            'payment': 700.0,
            'time': now - timedelta(days=10),
        })
        self.assertAlmostEqual(pos.quantity, 0.0)
        realized = pos.realized_ids.filtered(lambda r: not r.simulated)
        self.assertEqual(len(realized), 2)

    def test_fifo_partial_sell(self):
        """Partial sell creates simulated realization for remainder"""
        # The base position from common has 12 units remaining (10+5-3)
        # It should have a simulated sell for those 12 units
        simulated = self.position.realized_ids.filtered(lambda r: r.simulated)
        self.assertTrue(simulated, "Should have simulated realized records for remaining position")

    def test_realized_profit_calculation(self):
        """Verify sell_price, buy_price, profit on realized records"""
        pos = self.env['investment.position'].create({
            'name': 'FIFO Profit',
            'asset_id': self.asset.id,
            'portfolio_id': self.portfolio.id,
            'company_id': self.company.id,
        })
        now = datetime.now()
        self.env['investment.position.transaction'].create({
            'position_id': pos.id,
            'quantity': 10.0,
            'exchange_rate': 50.0,
            'payment': 500.0,
            'time': now - timedelta(days=20),
        })
        self.env['investment.position.transaction'].create({
            'position_id': pos.id,
            'quantity': -10.0,
            'exchange_rate': 80.0,
            'payment': 800.0,
            'time': now - timedelta(days=10),
        })
        # Force recomputation so realized records are created with real IDs
        pos._compute_position_aggregate()
        realized = pos.realized_ids.filtered(lambda r: not r.simulated)
        self.assertEqual(len(realized), 1)
        # sell_payment = 800, buy_payment = 500, no fees
        self.assertAlmostEqual(realized.sell_payment, 800.0, places=2)
        self.assertAlmostEqual(realized.buy_payment, 500.0, places=2)
        # profit = sell_price - sell_fee - buy_price - buy_fee
        # With no fees: sell_price = 800, buy_price = 500, profit = 800 - 500 = 300
        self.assertAlmostEqual(realized.profit, 300.0, places=2)

    def test_realized_cleanup_on_new_transaction(self):
        """Adding a transaction recomputes realized records"""
        pos = self.env['investment.position'].create({
            'name': 'FIFO Cleanup',
            'asset_id': self.asset.id,
            'portfolio_id': self.portfolio.id,
            'company_id': self.company.id,
        })
        now = datetime.now()
        self.env['investment.position.transaction'].create({
            'position_id': pos.id,
            'quantity': 10.0,
            'exchange_rate': 50.0,
            'payment': 500.0,
            'time': now - timedelta(days=20),
        })

        # Add a sell - realized records should be recomputed
        self.env['investment.position.transaction'].create({
            'position_id': pos.id,
            'quantity': -5.0,
            'exchange_rate': 60.0,
            'payment': 300.0,
            'time': now - timedelta(days=5),
        })
        # Force recomputation with real IDs
        pos._compute_position_aggregate()
        self.assertGreaterEqual(len(pos.realized_ids), 1)
