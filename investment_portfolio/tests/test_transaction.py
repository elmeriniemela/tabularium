# -*- coding: utf-8 -*-

from odoo.tests import tagged
from .common import InvestmentTestCommon
from datetime import datetime, timedelta


@tagged('post_install', '-at_install')
class TestTransaction(InvestmentTestCommon):

    def test_buy_classification(self):
        """qty > 0, payment > 0 => buy"""
        self.assertEqual(self.tx_buy1.ttype, 'buy')
        self.assertEqual(self.tx_buy2.ttype, 'buy')

    def test_sell_classification(self):
        """qty < 0, payment > 0 => sell"""
        self.assertEqual(self.tx_sell1.ttype, 'sell')

    def test_yield_classification(self):
        """qty = 0, payment > 0 => yield"""
        self.assertEqual(self.tx_yield1.ttype, 'yield')

    def test_cost_classification(self):
        """qty = 0, payment < 0 => cost"""
        tx_cost = self.env['investment.position.transaction'].create({
            'position_id': self.position.id,
            'quantity': 0.0,
            'exchange_rate': 0.0,
            'payment': -25.0,
            'time': datetime.now() - timedelta(days=2),
        })
        self.assertEqual(tx_cost.ttype, 'cost')

    def test_cost_classification_negative_qty(self):
        """qty < 0, payment <= 0 => cost"""
        tx_cost = self.env['investment.position.transaction'].create({
            'position_id': self.position.id,
            'quantity': -1.0,
            'exchange_rate': 0.0,
            'payment': -10.0,
            'time': datetime.now() - timedelta(days=1),
        })
        self.assertEqual(tx_cost.ttype, 'cost')

    def test_yield_classification(self):
        """qty > 0, payment = 0 => yield"""
        tx_split = self.env['investment.position.transaction'].create({
            'position_id': self.position.id,
            'quantity': 10.0,
            'exchange_rate': 0.0,
            'payment': 0.0,
            'time': datetime.now() - timedelta(days=1),
        })
        self.assertEqual(tx_split.ttype, 'yield')

    def test_cash_flow_buy(self):
        """Buy cash_flow = payment (positive, money flows into position)"""
        self.assertEqual(self.tx_buy1.cash_flow, 900.0)

    def test_cash_flow_sell(self):
        """Sell cash_flow = -payment (negative, money flows out)"""
        self.assertEqual(self.tx_sell1.cash_flow, -300.0)

    def test_cash_flow_yield(self):
        """Yield cash_flow = -payment (negative, money flows out)"""
        self.assertEqual(self.tx_yield1.cash_flow, -50.0)

    def test_fee_computation(self):
        """Fee = |payment/qty - exchange_rate| * qty (same currency)"""
        # Buy 10 @ 90 with total payment 910 => fee_per_unit = |910/10 - 90| = 1 => fee_currency = 10
        tx = self.env['investment.position.transaction'].create({
            'position_id': self.position.id,
            'quantity': 10.0,
            'exchange_rate': 90.0,
            'payment': 910.0,
            'time': datetime.now() - timedelta(days=3),
        })
        self.assertAlmostEqual(tx.fee_currency, 10.0, places=2)

    def test_fee_zero_when_no_fee(self):
        """Fee is 0 when payment/qty == exchange_rate"""
        self.assertAlmostEqual(self.tx_buy1.fee_currency, 0.0, places=2)

    def test_quantity_adjusted_no_split(self):
        """Without splits, quantity_adjusted == quantity"""
        self.assertAlmostEqual(self.tx_buy1.quantity_adjusted, 10.0)

    def test_quantity_adjusted_with_split(self):
        """Split factor applied to pre-split transactions"""
        now = datetime.now()
        split_price = self.env['investment.asset.price'].create({
            'asset_id': self.asset.id,
            'time': now - timedelta(days=5),
            'price': 50.0,
        })
        self.env['investment.asset.split'].create({
            'price_id': split_price.id,
            'factor': 2.0,
        })
        self.tx_buy1.invalidate_recordset(['quantity_adjusted'])
        # tx_buy1 was before the split, so adjusted = 10 * 2 = 20
        self.assertAlmostEqual(self.tx_buy1.quantity_adjusted, 20.0)

    def test_profit_computation(self):
        """Per-tx profit: (last_price - cost_per_unit) * quantity"""
        # tx_buy1: 10 units @ 90, last_price_own_currency = 100
        # profit = (100 - 90) * 10 = 100
        self.assertAlmostEqual(self.tx_buy1.profit, 100.0, places=2)
