# -*- coding: utf-8 -*-

from odoo.tests import tagged
from .common import InvestmentTestCommon
from datetime import datetime, timedelta


@tagged('post_install', '-at_install')
class TestTransactionAdvanced(InvestmentTestCommon):

    def test_cash_flow_cost_zero_qty(self):
        """Cost with qty=0: cash_flow = -payment (flips negative to positive)"""
        tx = self.env['investment.position.transaction'].create({
            'position_id': self.position.id,
            'quantity': 0.0,
            'exchange_rate': 0.0,
            'payment': -30.0,
            'time': datetime.now() - timedelta(days=2),
        })
        # payment is -30, cash_flow = -(-30) = 30
        self.assertEqual(tx.cash_flow, 30.0)

    def test_cash_flow_cost_negative_qty(self):
        """Cost with negative qty: cash_flow = -payment"""
        tx = self.env['investment.position.transaction'].create({
            'position_id': self.position.id,
            'quantity': -1.0,
            'exchange_rate': 0.0,
            'payment': -20.0,
            'time': datetime.now() - timedelta(days=2),
        })
        # payment is -20, cash_flow = -(-20) = 20
        self.assertEqual(tx.cash_flow, 20.0)

    def test_cash_flow_split(self):
        """Split transaction has zero cash_flow"""
        tx = self.env['investment.position.transaction'].create({
            'position_id': self.position.id,
            'quantity': 10.0,
            'exchange_rate': 0.0,
            'payment': 0.0,
            'time': datetime.now() - timedelta(days=2),
        })
        self.assertEqual(tx.cash_flow, 0.0)

    def test_prediction_from_usage(self):
        """prediction is True when usage='prediction'"""
        tx = self.env['investment.position.transaction'].create({
            'position_id': self.position.id,
            'quantity': 5.0,
            'exchange_rate': 100.0,
            'payment': 500.0,
            'time': datetime.now() + timedelta(days=30),
            'usage': 'prediction',
        })
        self.assertTrue(tx.prediction)

    def test_prediction_false_for_record(self):
        """prediction is False when usage='record'"""
        self.assertFalse(self.tx_buy1.prediction)

    def test_inverse_prediction_sets_usage(self):
        """Setting prediction=True sets usage='prediction'"""
        tx = self.env['investment.position.transaction'].create({
            'position_id': self.position.id,
            'quantity': 5.0,
            'exchange_rate': 100.0,
            'payment': 500.0,
            'time': datetime.now() + timedelta(days=30),
            'usage': 'record',
        })
        tx.prediction = True
        self.assertEqual(tx.usage, 'prediction')

    def test_display_name_format(self):
        """display_name includes position name and time"""
        self.tx_buy1._compute_display_name()
        self.assertIn('Test Position', self.tx_buy1.display_name)
        self.assertIn('@', self.tx_buy1.display_name)

    def test_profit_yield_transaction(self):
        """Yield transaction profit = payment (since qty=0)"""
        self.tx_yield1._compute_profit()
        self.assertAlmostEqual(self.tx_yield1.profit, 50.0, places=2)

    def test_profit_sell_transaction(self):
        """Sell profit = (last_price_own_currency - payment/|qty|) * qty"""
        # tx_sell1: qty=-3, payment=300, exchange_rate=100
        # quantity_adjusted = -3 (no splits)
        # profit = (100 - 300/3) * (-3) = (100 - 100) * (-3) = 0
        self.tx_sell1._compute_profit()
        self.assertAlmostEqual(self.tx_sell1.profit, 0.0, places=2)

    def test_profit_buy_with_gain(self):
        """Buy profit when price has risen"""
        # tx_buy1: qty=10, payment=900, exchange_rate=90
        # profit = (100 - 900/10) * 10 = (100-90)*10 = 100
        self.tx_buy1._compute_profit()
        self.assertAlmostEqual(self.tx_buy1.profit, 100.0, places=2)

    def test_profit_buy2_with_gain(self):
        """Buy2 profit reflects price change"""
        # tx_buy2: qty=5, payment=475, exchange_rate=95
        # profit = (100 - 475/5) * 5 = (100-95)*5 = 25
        self.tx_buy2._compute_profit()
        self.assertAlmostEqual(self.tx_buy2.profit, 25.0, places=2)

    def test_profit_split_is_zero(self):
        """Split transaction has zero profit"""
        tx = self.env['investment.position.transaction'].create({
            'position_id': self.position.id,
            'quantity': 10.0,
            'exchange_rate': 0.0,
            'payment': 0.0,
            'time': datetime.now() - timedelta(days=2),
        })
        tx._compute_profit()
        self.assertAlmostEqual(tx.profit, 0.0, places=2)

    def test_fee_with_different_exchange_rate(self):
        """Fee calculated from payment/qty vs exchange_rate difference"""
        # Buy 5 @ exchange_rate=90, but payment=500 (so 100/unit)
        # fee = |500/5 - 90| * 5 = |100-90| * 5 = 50
        tx = self.env['investment.position.transaction'].create({
            'position_id': self.position.id,
            'quantity': 5.0,
            'exchange_rate': 90.0,
            'payment': 500.0,
            'time': datetime.now() - timedelta(days=3),
        })
        self.assertAlmostEqual(tx.fee, 50.0, places=2)

    def test_fee_sell_transaction(self):
        """Fee on sell transaction"""
        # Sell 3 @ exchange_rate=100, payment=330 (110/unit)
        # fee = |330/3 - 100| * 3 = 10 * 3 = 30
        tx = self.env['investment.position.transaction'].create({
            'position_id': self.position.id,
            'quantity': -3.0,
            'exchange_rate': 100.0,
            'payment': 330.0,
            'time': datetime.now() - timedelta(days=3),
        })
        self.assertAlmostEqual(tx.fee, 30.0, places=2)

    def test_payment_currency_same_currency(self):
        """Same currency: payment_currency = payment"""
        self.tx_buy1._compute_payment_currency()
        self.assertAlmostEqual(self.tx_buy1.payment_currency, 900.0, places=2)

    def test_fee_uses_asset_currency_when_company_differs(self):
        """Fee compute/inverse uses asset currency when currencies differ"""
        usd = self.env.ref('base.USD')
        now = datetime.now()
        rate = self.env['res.currency.rate'].search([
            ('name', '=', now.date()),
            ('currency_id', '=', usd.id),
            ('company_id', '=', self.company.id),
        ], limit=1)
        if rate:
            rate.inverse_company_rate = 0.5  # 1 USD = 0.5 EUR -> 1 EUR = 2 USD
        else:
            self.env['res.currency.rate'].create({
                'name': now.date(),
                'currency_id': usd.id,
                'company_id': self.company.id,
                'inverse_company_rate': 0.5,
            })
        asset_usd = self.env['investment.asset'].create({
            'ticker': 'TEST-USD',
            'category_id': self.category.id,
            'currency_id': usd.id,
            'expected_yearly_appreciation': 0.10,
            'plausible_ath_drawdown': 0.30,
        })
        position_usd = self.env['investment.position'].create({
            'name': 'USD Position',
            'asset_id': asset_usd.id,
            'portfolio_id': self.portfolio.id,
            'company_id': self.company.id,
        })
        tx = self.env['investment.position.transaction'].create({
            'position_id': position_usd.id,
            'quantity': 5.0,
            'exchange_rate': 90.0,
            'payment': 250.0,  # 500 USD payment_currency at the configured FX rate
            'time': now - timedelta(days=1),
        })

        # fee = |payment_currency/qty - exchange_rate| * qty, in asset currency
        expected_fee = abs(tx.payment_currency / 5.0 - 90.0) * 5.0
        self.assertAlmostEqual(tx.fee, expected_fee, places=2)
        self.assertEqual(tx._fields['fee'].currency_field, 'currency_id')

        # inverse: exchange_rate = payment_currency/qty - fee/qty, in asset currency
        tx.fee = 25.0
        expected_exchange_rate = tx.payment_currency / 5.0 - 25.0 / 5.0
        self.assertAlmostEqual(tx.exchange_rate, expected_exchange_rate, places=2)

    def test_quantity_adjusted_multiple_splits(self):
        """Multiple splits compound on quantity adjustment"""
        now = datetime.now()
        # Split at -20d, factor 2
        sp1 = self.env['investment.asset.price'].create({
            'asset_id': self.asset.id,
            'time': now - timedelta(days=20),
            'price': 50.0,
        })
        self.env['investment.asset.split'].create({'price_id': sp1.id, 'factor': 2.0})
        # Split at -10d, factor 3
        sp2 = self.env['investment.asset.price'].create({
            'asset_id': self.asset.id,
            'time': now - timedelta(days=10),
            'price': 25.0,
        })
        self.env['investment.asset.split'].create({'price_id': sp2.id, 'factor': 3.0})
        # tx_buy1 (qty=10 @ -60d) is before both splits: adjusted = 10 * 2 * 3 = 60
        self.tx_buy1.invalidate_recordset(['quantity_adjusted'])
        self.assertAlmostEqual(self.tx_buy1.quantity_adjusted, 60.0)

    def test_make_move_creates_move(self):
        """make_move creates a position.move from transactions"""
        result = self.tx_buy1.make_move()
        self.assertEqual(result['res_model'], 'investment.position.move')
        move = self.env['investment.position.move'].browse(result['res_id'])
        self.assertIn(self.tx_buy1, move.transaction_ids)

    def test_make_move_raises_if_already_has_move(self):
        """make_move raises if transaction already has a move"""
        self.tx_buy1.make_move()
        with self.assertRaises(Exception):
            self.tx_buy1.make_move()
