# -*- coding: utf-8 -*-

from odoo.tests import tagged
from .common import InvestmentTestCommon
from datetime import datetime, timedelta


@tagged('post_install', '-at_install')
class TestMove(InvestmentTestCommon):

    def test_move_auto_name(self):
        """Move gets auto-generated MOVE/{year}/{number} name"""
        move = self.env['investment.position.move'].create({
            'time': datetime.now(),
            'company_id': self.company.id,
        })
        self.assertTrue(move.name.startswith('MOVE/'))
        parts = move.name.split('/')
        self.assertEqual(len(parts), 3)
        self.assertEqual(parts[0], 'MOVE')

    def test_move_sequential_names(self):
        """Multiple moves get sequential numbers"""
        now = datetime.now()
        m1 = self.env['investment.position.move'].create({
            'time': now,
            'company_id': self.company.id,
        })
        m2 = self.env['investment.position.move'].create({
            'time': now,
            'company_id': self.company.id,
        })
        num1 = int(m1.name.split('/')[-1])
        num2 = int(m2.name.split('/')[-1])
        self.assertEqual(num2, num1 + 1)

    def test_move_cash_flow(self):
        """Move cash_flow is sum of transaction cash_flows"""
        now = datetime.now()
        # Create a move with buy and sell
        move = self.env['investment.position.move'].create({
            'time': now,
            'company_id': self.company.id,
        })
        self.tx_buy1.move_id = move
        self.tx_sell1.move_id = move
        move.invalidate_recordset(['cash_flow'])
        # buy1 cash_flow=900, sell1 cash_flow=-300 => net = 600
        self.assertAlmostEqual(move.cash_flow, 600.0, places=2)

    def test_move_profit(self):
        """Move profit is sum of transaction profits"""
        now = datetime.now()
        move = self.env['investment.position.move'].create({
            'time': now,
            'company_id': self.company.id,
        })
        self.tx_buy1.move_id = move
        move.invalidate_recordset(['profit'])
        # tx_buy1 profit = (100-90)*10 = 100
        self.assertAlmostEqual(move.profit, 100.0, places=2)

    def test_move_position_ids(self):
        """Move position_ids are derived from transactions"""
        now = datetime.now()
        move = self.env['investment.position.move'].create({
            'time': now,
            'company_id': self.company.id,
        })
        self.tx_buy1.move_id = move
        move.invalidate_recordset(['position_ids'])
        self.assertIn(self.position, move.position_ids)
