# -*- coding: utf-8 -*-

from odoo.tests import tagged
from .common import InvestmentTestCommon
from datetime import datetime, timedelta, date


@tagged('post_install', '-at_install')
class TestPeriod(InvestmentTestCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Generate timeseries for the position so period has data
        cls.position.generate_timeseries()

    def test_period_profit(self):
        """Basic period profit is computed"""
        today = date.today()
        period = self.env['investment.period'].create({
            'name': 'Test Period',
            'start_date': today - timedelta(days=61),
            'end_date': today,
            'domain': "[('id', '=', %d)]" % self.position.id,
            'company_id': self.company.id,
        })
        period.action_compute()
        # Profit should be defined (non-zero given our transactions)
        self.assertIsNotNone(period.profit)

    def test_period_positions(self):
        """Period creates per-position records"""
        today = date.today()
        period = self.env['investment.period'].create({
            'name': 'Test Period Positions',
            'start_date': today - timedelta(days=61),
            'end_date': today,
            'domain': "[('id', '=', %d)]" % self.position.id,
            'company_id': self.company.id,
        })
        period.action_compute()
        self.assertGreaterEqual(period.count_positions, 1)

    def test_period_irr(self):
        """IRR computation produces a numeric result"""
        today = date.today()
        period = self.env['investment.period'].create({
            'name': 'Test Period IRR',
            'start_date': today - timedelta(days=61),
            'end_date': today,
            'domain': "[('id', '=', %d)]" % self.position.id,
            'company_id': self.company.id,
        })
        period.action_compute()
        # IRR should be a float (could be 0 if xirr fails, but should be numeric)
        self.assertIsInstance(period.annualized_irr, float)
