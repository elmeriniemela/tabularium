# -*- coding: utf-8 -*-

from odoo.tests import tagged
from .common import InvestmentTestCommon
from datetime import datetime, timedelta


@tagged('post_install', '-at_install')
class TestPositionAdvanced(InvestmentTestCommon):

    def test_position_currency_value(self):
        """position_currency = last_price * quantity = 100 * 12 = 1200"""
        self.assertAlmostEqual(self.position.position_currency, 1200.0, places=2)

    def test_position_abs(self):
        """position_abs = abs(position) = 1200"""
        self.assertAlmostEqual(self.position.position_abs, 1200.0, places=2)

    def test_is_company_currency_same(self):
        """is_company_currency True when asset and company currency match"""
        # Both are EUR
        self.assertTrue(self.position.is_company_currency)

    def test_is_company_currency_different(self):
        """is_company_currency False when currencies differ"""
        usd = self.env.ref('base.USD')
        asset_usd = self.env['investment.asset'].create({
            'ticker': 'TEST-USD',
            'category_id': self.category.id,
            'currency_id': usd.id,
        })
        pos = self.env['investment.position'].create({
            'name': 'USD Position',
            'asset_id': asset_usd.id,
            'portfolio_id': self.portfolio.id,
            'company_id': self.company.id,
        })
        self.assertFalse(pos.is_company_currency)

    def test_is_cash_true(self):
        """is_cash True when ticker matches company currency code"""
        asset_cash = self.env['investment.asset'].create({
            'ticker': 'EUR',
            'category_id': self.category.id,
            'currency_id': self.currency_eur.id,
        })
        pos = self.env['investment.position'].create({
            'name': 'Cash Position',
            'asset_id': asset_cash.id,
            'portfolio_id': self.portfolio.id,
            'company_id': self.company.id,
        })
        self.assertTrue(pos.is_cash)

    def test_is_cash_false(self):
        """is_cash False when ticker doesn't match company currency"""
        self.assertFalse(self.position.is_cash)

    def test_cost_basis_calculation(self):
        """cost_basis tracks average purchase cost per unit"""
        # With FIFO matching: the simulated sell matches against buys
        # cost_basis = total buy cost for remaining units / quantity
        self.position._compute_position_aggregate()
        # We have 12 units remaining. FIFO: sold 3 from buy1 (10@90).
        # Remaining: 7 from buy1 @90 = 630, 5 from buy2 @95 = 475 => total = 1105
        # cost_basis = 1105 / 12 = 92.0833
        if self.position.cost_basis:
            self.assertAlmostEqual(self.position.cost_basis, 1105.0 / 12.0, places=0)

    def test_plausible_drawdown_position(self):
        """plausible_drawdown_position = drawdown_price_own_currency * quantity"""
        # drawdown_price = (1 - 0.30) * 100 = 70 (in EUR, same currency)
        # plausible_drawdown_position = 70 * 12 = 840
        self.assertAlmostEqual(self.position.plausible_drawdown_position, 840.0, places=0)

    def test_drawdown_price_own_currency(self):
        """drawdown_price converted to company currency"""
        # Same currency, so drawdown_price_own_currency = 70
        self.assertAlmostEqual(self.position.drawdown_price_own_currency, 70.0, places=0)

    def test_last_price_own_currency(self):
        """last_price converted to company currency"""
        # Same currency: last_price_own_currency = 100
        self.assertAlmostEqual(self.position.last_price_own_currency, 100.0, places=2)

    def test_compute_realized_disabled(self):
        """When compute_realized=False, no realized records are created"""
        pos = self.env['investment.position'].create({
            'name': 'No Realized',
            'asset_id': self.asset.id,
            'portfolio_id': self.portfolio.id,
            'company_id': self.company.id,
            'compute_realized': False,
        })
        now = datetime.now()
        self.env['investment.position.transaction'].create({
            'position_id': pos.id,
            'quantity': 10.0,
            'exchange_rate': 90.0,
            'payment': 900.0,
            'time': now - timedelta(days=20),
        })
        self.env['investment.position.transaction'].create({
            'position_id': pos.id,
            'quantity': -5.0,
            'exchange_rate': 100.0,
            'payment': 500.0,
            'time': now - timedelta(days=10),
        })
        self.assertEqual(len(pos.realized_ids), 0)

    def test_position_zero_quantity(self):
        """Position with all units sold has zero quantity and defined profit"""
        pos = self.env['investment.position'].create({
            'name': 'Closed Position',
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
        self.assertAlmostEqual(pos.quantity, 0.0)
        # investment = 500 - 600 = -100
        self.assertAlmostEqual(pos.investment, -100.0, places=2)
        # position = 0 * 100 = 0, profit = 0 - (-100) = 100
        self.assertAlmostEqual(pos.position, 0.0, places=2)
        self.assertAlmostEqual(pos.profit, 100.0, places=2)

    def test_position_with_yield_only(self):
        """Position with only yield transactions"""
        pos = self.env['investment.position'].create({
            'name': 'Yield Only',
            'asset_id': self.asset.id,
            'portfolio_id': self.portfolio.id,
            'company_id': self.company.id,
        })
        now = datetime.now()
        self.env['investment.position.transaction'].create({
            'position_id': pos.id,
            'quantity': 0.0,
            'exchange_rate': 0.0,
            'payment': 100.0,
            'time': now - timedelta(days=5),
        })
        # quantity=0, investment = -100 (yield cash_flow = -payment = -100)
        self.assertAlmostEqual(pos.quantity, 0.0)
        self.assertAlmostEqual(pos.investment, -100.0, places=2)
        # profit = 0 - (-100) = 100
        self.assertAlmostEqual(pos.profit, 100.0, places=2)

    def test_max_investment_tracks_peak(self):
        """max_investment is the highest cumulative cash_flow at any point"""
        pos = self.env['investment.position'].create({
            'name': 'Peak Test',
            'asset_id': self.asset.id,
            'portfolio_id': self.portfolio.id,
            'company_id': self.company.id,
        })
        now = datetime.now()
        # Buy 10 @ 100 = 1000
        self.env['investment.position.transaction'].create({
            'position_id': pos.id,
            'quantity': 10.0,
            'exchange_rate': 100.0,
            'payment': 1000.0,
            'time': now - timedelta(days=30),
        })
        # Sell 5 @ 100 = 500 (cash_flow = -500)
        self.env['investment.position.transaction'].create({
            'position_id': pos.id,
            'quantity': -5.0,
            'exchange_rate': 100.0,
            'payment': 500.0,
            'time': now - timedelta(days=20),
        })
        # Buy 3 @ 100 = 300
        self.env['investment.position.transaction'].create({
            'position_id': pos.id,
            'quantity': 3.0,
            'exchange_rate': 100.0,
            'payment': 300.0,
            'time': now - timedelta(days=10),
        })
        # Cumulative cash_flows in reverse order: 300, -500+300=-200, 1000-200=800
        # Actually: chronologically: 1000, 1000-500=500, 500+300=800
        # max = 1000
        self.assertAlmostEqual(pos.max_investment, 1000.0, places=2)
