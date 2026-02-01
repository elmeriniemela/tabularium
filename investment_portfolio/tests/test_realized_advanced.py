# -*- coding: utf-8 -*-

from odoo.tests import tagged
from .common import InvestmentTestCommon
from datetime import datetime, timedelta


@tagged('post_install', '-at_install')
class TestRealizedAdvanced(InvestmentTestCommon):

    def test_simulated_flag(self):
        """Simulated realized records have simulated=True"""
        # The base position has 12 remaining units -> simulated sell
        simulated = self.position.realized_ids.filtered(lambda r: r.simulated)
        self.assertTrue(simulated)
        for rec in simulated:
            self.assertTrue(rec.simulated)

    def test_non_simulated_flag(self):
        """Real realized records have simulated=False"""
        # tx_sell1 sold 3 units from buy1, this should be a real realized
        non_simulated = self.position.realized_ids.filtered(lambda r: not r.simulated)
        for rec in non_simulated:
            self.assertFalse(rec.simulated)

    def test_fifo_sell_dates(self):
        """Realized sell_date and buy_date match transaction dates"""
        pos = self.env['investment.position'].create({
            'name': 'FIFO Dates',
            'asset_id': self.asset.id,
            'portfolio_id': self.portfolio.id,
            'company_id': self.company.id,
        })
        now = datetime.now()
        buy_time = now - timedelta(days=20)
        sell_time = now - timedelta(days=10)
        self.env['investment.position.transaction'].create({
            'position_id': pos.id,
            'quantity': 10.0,
            'exchange_rate': 50.0,
            'payment': 500.0,
            'time': buy_time,
        })
        self.env['investment.position.transaction'].create({
            'position_id': pos.id,
            'quantity': -10.0,
            'exchange_rate': 60.0,
            'payment': 600.0,
            'time': sell_time,
        })
        pos._compute_position_aggregate()
        realized = pos.realized_ids.filtered(lambda r: not r.simulated)
        self.assertEqual(len(realized), 1)
        self.assertEqual(realized.buy_date, buy_time.date())
        self.assertEqual(realized.sell_date, sell_time.date())

    def test_fifo_partial_quantities(self):
        """FIFO matching correctly splits across buys"""
        pos = self.env['investment.position'].create({
            'name': 'FIFO Partial Qty',
            'asset_id': self.asset.id,
            'portfolio_id': self.portfolio.id,
            'company_id': self.company.id,
        })
        now = datetime.now()
        # Buy 5 @ 40
        self.env['investment.position.transaction'].create({
            'position_id': pos.id,
            'quantity': 5.0,
            'exchange_rate': 40.0,
            'payment': 200.0,
            'time': now - timedelta(days=30),
        })
        # Buy 10 @ 50
        self.env['investment.position.transaction'].create({
            'position_id': pos.id,
            'quantity': 10.0,
            'exchange_rate': 50.0,
            'payment': 500.0,
            'time': now - timedelta(days=20),
        })
        # Sell 8 @ 60
        self.env['investment.position.transaction'].create({
            'position_id': pos.id,
            'quantity': -8.0,
            'exchange_rate': 60.0,
            'payment': 480.0,
            'time': now - timedelta(days=10),
        })
        pos._compute_position_aggregate()
        realized = pos.realized_ids.filtered(lambda r: not r.simulated)
        # FIFO: 5 from buy1, 3 from buy2 => 2 realized records
        self.assertEqual(len(realized), 2)
        quantities = sorted(realized.mapped('quantity'))
        self.assertAlmostEqual(quantities[0], 3.0)
        self.assertAlmostEqual(quantities[1], 5.0)

    def test_realized_profit_with_fee(self):
        """Realized profit accounts for fees"""
        pos = self.env['investment.position'].create({
            'name': 'FIFO Fee',
            'asset_id': self.asset.id,
            'portfolio_id': self.portfolio.id,
            'company_id': self.company.id,
        })
        now = datetime.now()
        # Buy 10 @ exchange_rate=50, payment=520 (fee = |520/10-50|*10 = 20)
        self.env['investment.position.transaction'].create({
            'position_id': pos.id,
            'quantity': 10.0,
            'exchange_rate': 50.0,
            'payment': 520.0,
            'time': now - timedelta(days=20),
        })
        # Sell 10 @ exchange_rate=60, payment=580 (fee = |580/10-60|*10 = 20)
        self.env['investment.position.transaction'].create({
            'position_id': pos.id,
            'quantity': -10.0,
            'exchange_rate': 60.0,
            'payment': 580.0,
            'time': now - timedelta(days=10),
        })
        pos._compute_position_aggregate()
        realized = pos.realized_ids.filtered(lambda r: not r.simulated)
        self.assertEqual(len(realized), 1)
        # sell_payment = 580, buy_payment = 520
        self.assertAlmostEqual(realized.sell_payment, 580.0, places=2)
        self.assertAlmostEqual(realized.buy_payment, 520.0, places=2)
        # sell_fee = 20, buy_fee = 20
        self.assertAlmostEqual(realized.sell_fee, 20.0, places=2)
        self.assertAlmostEqual(realized.buy_fee, 20.0, places=2)
        # sell_price = sell_payment + sell_fee = 580 + 20 = 600
        self.assertAlmostEqual(realized.sell_price, 600.0, places=2)
        # buy_price = buy_payment - buy_fee = 520 - 20 = 500
        self.assertAlmostEqual(realized.buy_price, 500.0, places=2)
        # profit = sell_price - sell_fee - buy_price - buy_fee
        # = 600 - 20 - 500 - 20 = 60
        self.assertAlmostEqual(realized.profit, 60.0, places=2)

    def test_realized_payment_currency(self):
        """Realized buy/sell_payment_currency in asset currency (same as company)"""
        pos = self.env['investment.position'].create({
            'name': 'FIFO Currency',
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
        pos._compute_position_aggregate()
        realized = pos.realized_ids.filtered(lambda r: not r.simulated)
        # Same currency: payment_currency = payment
        self.assertAlmostEqual(realized.sell_payment_currency, 600.0, places=2)
        self.assertAlmostEqual(realized.buy_payment_currency, 500.0, places=2)
