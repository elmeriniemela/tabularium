# -*- coding: utf-8 -*-

import csv
import json
from datetime import date, timedelta
from unittest.mock import patch

from odoo.tests import tagged
from odoo.tools import file_open

from odoo.addons.investment_portfolio.models.investment_timeseries import InvestmentTimeseries
from .common import InvestmentTestCommon

from odoo.addons.investment_portfolio.models.investment_period import xirr


XIRR_VECTOR_FILE = 'investment_portfolio/tests/xirr-test-vectors.csv'


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

    def test_xirr_known_cash_flows_and_invalid_values(self):
        result = xirr(
            [date(2020, 1, 1), date(2021, 1, 1)],
            [-1000, 1100],
        )
        self.assertAlmostEqual(result, 0.0997135859, places=8)

        with self.assertRaises(ValueError):
            xirr([date(2020, 1, 1), date(2021, 1, 1)], [1000, 1100])

    def test_xirr_synthetic_regression_vectors(self):
        with file_open(XIRR_VECTOR_FILE) as vector_file:
            vectors = list(csv.DictReader(vector_file))
        self.assertTrue(vectors, "The XIRR regression vector file is empty")

        for index, vector in enumerate(vectors, start=1):
            dates = [date.fromisoformat(value) for value in json.loads(vector['dates'])]
            values = json.loads(vector['values'])
            expected = float(vector['expected_xirr'])

            with self.subTest(case=vector['case'], vector=index, cash_flows=len(values)):
                self.assertEqual(len(dates), len(values))
                # _compute_period only invokes xirr() for non-empty cash flows.
                actual = xirr(dates, values) if values else 0.0
                self.assertAlmostEqual(actual, expected, delta=1e-9)

    def test_future_period_batch_recomputes_end_series_once(self):
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
        original_compute = InvestmentTimeseries._compute_timeseries_aggregate

        with patch(
            'odoo.addons.investment_portfolio.models.investment_timeseries.InvestmentTimeseries._compute_timeseries_aggregate',
            autospec=True,
            side_effect=original_compute,
        ) as compute_aggregate:
            periods._compute_period()

        self.assertEqual(compute_aggregate.call_count, 1)
