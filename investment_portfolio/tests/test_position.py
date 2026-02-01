# -*- coding: utf-8 -*-

from odoo.tests import tagged
from .common import InvestmentTestCommon
from datetime import datetime, timedelta


@tagged('post_install', '-at_install')
class TestPosition(InvestmentTestCommon):

    def test_get_position_quantity(self):
        """Verify quantity from _get_position: 10 + 5 - 3 = 12"""
        self.assertAlmostEqual(self.position.quantity, 12.0)

    def test_get_position_investment(self):
        """Investment = sum of cash_flows: 900 + 475 - 300 - 50 = 1025"""
        self.assertAlmostEqual(self.position.investment, 1025.0, places=2)

    def test_get_position_value(self):
        """Position value = quantity * last_price_own_currency = 12 * 100 = 1200"""
        self.assertAlmostEqual(self.position.position, 1200.0, places=2)

    def test_get_position_profit(self):
        """Profit = position - investment = 1200 - 1025 = 175"""
        self.assertAlmostEqual(self.position.profit, 175.0, places=2)

    def test_get_position_max_investment(self):
        """Max investment tracks running maximum of cumulative cash_flows"""
        # After buy1: 900, after buy2: 1375, after sell: 1075, after yield: 1025
        # max = 1375
        self.assertAlmostEqual(self.position.max_investment, 1375.0, places=2)

    def test_get_position_profit_percent(self):
        """profit_percent = profit / max_investment = 175 / 1375"""
        expected = 175.0 / 1375.0
        self.assertAlmostEqual(self.position.profit_percent, expected, places=4)

    def test_position_buy_only(self):
        """Position with only buys"""
        pos = self.env['investment.position'].create({
            'name': 'Buy Only',
            'asset_id': self.asset.id,
            'portfolio_id': self.portfolio.id,
            'company_id': self.company.id,
        })
        self.env['investment.position.transaction'].create({
            'position_id': pos.id,
            'quantity': 5.0,
            'exchange_rate': 100.0,
            'payment': 500.0,
            'time': datetime.now() - timedelta(days=10),
        })
        self.assertAlmostEqual(pos.quantity, 5.0)
        self.assertAlmostEqual(pos.investment, 500.0, places=2)

    def test_inverse_quantity(self):
        """Setting quantity creates balancing transaction"""
        initial_tx_count = len(self.position.transaction_ids)
        self.position.quantity = 20.0
        self.assertGreater(len(self.position.transaction_ids), initial_tx_count)
        self.assertAlmostEqual(self.position.quantity, 20.0)
