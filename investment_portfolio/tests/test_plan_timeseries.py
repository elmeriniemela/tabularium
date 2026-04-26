# -*- coding: utf-8 -*-

from datetime import date, datetime

from odoo.tests import tagged

from .common import InvestmentTestCommon


@tagged('post_install', '-at_install')
class TestPlanTimeseries(InvestmentTestCommon):

    def test_timeseries_aggregate_cutoff(self):
        """Timeseries aggregates only transactions up to its date."""
        pos = self.env['investment.position'].create({
            'name': 'Timeseries Cutoff',
            'asset_id': self.asset.id,
            'portfolio_id': self.portfolio.id,
            'company_id': self.company.id,
        })
        tx_early = self.env['investment.position.transaction'].create({
            'position_id': pos.id,
            'quantity': 10.0,
            'exchange_rate': 100.0,
            'payment': 1000.0,
            'time': datetime(2024, 1, 10, 12, 0, 0),
        })
        tx_late = self.env['investment.position.transaction'].create({
            'position_id': pos.id,
            'quantity': -5.0,
            'exchange_rate': 100.0,
            'payment': 500.0,
            'time': datetime(2024, 2, 10, 12, 0, 0),
        })
        price = self.env['investment.asset.price'].create({
            'asset_id': self.asset.id,
            'time': datetime(2024, 1, 15, 12, 0, 0),
            'price': 100.0,
        })
        ts = self.env['investment.timeseries'].create({
            'position_id': pos.id,
            'date': date(2024, 1, 15),
            'price_id': price.id,
        })
        ts._compute_timeseries_aggregate()
        self.assertIn(tx_early, ts.transaction_ids)
        self.assertNotIn(tx_late, ts.transaction_ids)
        self.assertAlmostEqual(ts.quantity, 10.0, places=2)
        self.assertAlmostEqual(ts.position, 1000.0, places=2)
        self.assertAlmostEqual(ts.profit, 0.0, places=2)

    def test_timeseries_formatted_read_group_filters_granularity(self):
        """formatted_read_group adds a granularity filter based on date group."""
        pos = self.env['investment.position'].create({
            'name': 'Timeseries Group',
            'asset_id': self.asset.id,
            'portfolio_id': self.portfolio.id,
            'company_id': self.company.id,
        })
        month_end_price = self.env['investment.asset.price'].create({
            'asset_id': self.asset.id,
            'time': datetime(2024, 1, 31, 12, 0, 0),
            'price': 100.0,
        })
        daily_price = self.env['investment.asset.price'].create({
            'asset_id': self.asset.id,
            'time': datetime(2024, 2, 15, 12, 0, 0),
            'price': 100.0,
        })
        self.env['investment.timeseries'].create({
            'position_id': pos.id,
            'date': date(2024, 1, 31),
            'price_id': month_end_price.id,
        })
        self.env['investment.timeseries'].create({
            'position_id': pos.id,
            'date': date(2024, 2, 15),
            'price_id': daily_price.id,
        })

        result = self.env['investment.timeseries'].formatted_read_group(
            domain=[('position_id', '=', pos.id)],
            groupby=['date:month'],
            aggregates=['position_id:count'],
        )
        groups = result
        self.assertEqual(len(groups), 1)
        group_date = groups[0]['date:month']
        if isinstance(group_date, tuple):
            group_date = group_date[0]
        if isinstance(group_date, str):
            group_date = date.fromisoformat(group_date)
        self.assertEqual(group_date.month, 1)

    def test_generate_plan_acquire_creates_predictions(self):
        """Acquire plan creates prediction transactions and sums cash flow."""
        asset = self.env['investment.asset'].create({
            'ticker': 'PLAN-ACQUIRE',
            'category_id': self.category.id,
            'currency_id': self.currency_eur.id,
            'expected_yearly_appreciation': 0.0,
        })
        asset_price = self.env['investment.asset.price'].create({
            'asset_id': asset.id,
            'time': datetime(2024, 1, 1, 12, 0, 0),
            'price': 100.0,
        })
        asset.last_price_id = asset_price
        pos = self.env['investment.position'].create({
            'name': 'Plan Acquire',
            'asset_id': asset.id,
            'portfolio_id': self.portfolio.id,
            'company_id': self.company.id,
            'plan_type': 'acquire',
            'plan_start_date': date(2024, 1, 1),
            'plan_allow_past': True,
            'plan_months': 2,
            'plan_payment': 100.0,
            'plan_yield': 10.0,
            'plan_cost': 5.0,
            'plan_fee': 0.0,
        })
        self.env['investment.position.transaction'].create({
            'position_id': pos.id,
            'quantity': 5.0,
            'exchange_rate': 100.0,
            'payment': 500.0,
            'time': datetime(2023, 12, 1, 12, 0, 0),
        })
        pos._compute_position_aggregate()
        pos.generate_plan()
        predictions = self.env['investment.position.transaction'].search([
            ('position_id', '=', pos.id),
            ('prediction', '=', True),
        ])
        self.assertEqual(len(predictions), 6)
        expected_cash_flow = 2 * (100.0 - 10.0 + 5.0)
        self.assertAlmostEqual(pos.plan_total_cash_flow, expected_cash_flow, places=2)

    def test_generate_plan_exit_sets_payment_and_sells(self):
        """Exit plan computes a payment and creates sell predictions."""
        asset = self.env['investment.asset'].create({
            'ticker': 'PLAN-EXIT',
            'category_id': self.category.id,
            'currency_id': self.currency_eur.id,
            'expected_yearly_appreciation': 0.0,
        })
        asset_price = self.env['investment.asset.price'].create({
            'asset_id': asset.id,
            'time': datetime(2024, 1, 1, 12, 0, 0),
            'price': 100.0,
        })
        asset.last_price_id = asset_price
        pos = self.env['investment.position'].create({
            'name': 'Plan Exit',
            'asset_id': asset.id,
            'portfolio_id': self.portfolio.id,
            'company_id': self.company.id,
            'plan_type': 'exit',
            'plan_start_date': date(2024, 1, 1),
            'plan_allow_past': True,
            'plan_months': 2,
            'plan_yearly_interest': 0.12,
            'plan_fee': 0.0,
        })
        self.env['investment.position.transaction'].create({
            'position_id': pos.id,
            'quantity': 10.0,
            'exchange_rate': 100.0,
            'payment': 1000.0,
            'time': datetime(2023, 12, 1, 12, 0, 0),
        })
        pos._compute_position_aggregate()
        pos.generate_plan()
        r = pos.plan_yearly_interest / 12.0
        pv = pos.position
        expected_payment = (r * pv) / (1 - (1 + r) ** (-pos.plan_months))
        self.assertAlmostEqual(pos.plan_payment, expected_payment, places=2)
        predictions = self.env['investment.position.transaction'].search([
            ('position_id', '=', pos.id),
            ('prediction', '=', True),
        ], order='time asc')
        self.assertTrue(predictions)
        self.assertTrue(any(tx.quantity < 0 for tx in predictions))
        self.assertTrue(any(tx.ttype == 'sell' for tx in predictions))
        self.assertLess(pos.plan_total_cash_flow, 0.0)
