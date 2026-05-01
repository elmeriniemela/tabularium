# -*- coding: utf-8 -*-

from odoo.tests import tagged
from odoo.addons.investment_portfolio.models.investment_timeseries import InvestmentTimeseries
from .common import InvestmentTestCommon
from datetime import datetime, timedelta, date
from unittest.mock import patch


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

    def test_future_period_batch_refreshes_end_series_once(self):
        today = date.today()
        periods = self.env['investment.period'].create([
            {
                'name': 'Future Batch A',
                'start_date': today - timedelta(days=61),
                'end_date': today + timedelta(days=7),
                'domain': "[('id', '=', %d)]" % self.position.id,
                'company_id': self.company.id,
            },
            {
                'name': 'Future Batch B',
                'start_date': today - timedelta(days=31),
                'end_date': today + timedelta(days=14),
                'domain': "[('id', '=', %d)]" % self.position.id,
                'company_id': self.company.id,
            },
        ])
        self.env.flush_all()
        original_refresh_price = InvestmentTimeseries.refresh_price
        original_compute = InvestmentTimeseries._compute_timeseries_aggregate

        with patch(
            'odoo.addons.investment_portfolio.models.investment_timeseries.InvestmentTimeseries.refresh_price',
            autospec=True,
            side_effect=original_refresh_price,
        ) as refresh_price, patch(
            'odoo.addons.investment_portfolio.models.investment_timeseries.InvestmentTimeseries._compute_timeseries_aggregate',
            autospec=True,
            side_effect=original_compute,
        ) as compute_aggregate:
            periods._compute_period()

        self.assertEqual(refresh_price.call_count, 1)
        self.assertEqual(compute_aggregate.call_count, 1)
