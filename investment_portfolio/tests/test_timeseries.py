# -*- coding: utf-8 -*-

from odoo.tests import tagged
from .common import InvestmentTestCommon
from datetime import date, datetime, timedelta


@tagged('post_install', '-at_install')
class TestTimeseries(InvestmentTestCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.position.generate_timeseries()

    def test_timeseries_created(self):
        """generate_timeseries creates records from first transaction to today"""
        series = self.env['investment.timeseries'].search([
            ('position_id', '=', self.position.id),
        ])
        self.assertTrue(series)

    def test_timeseries_today_exists(self):
        """Today's timeseries entry exists"""
        today = date.today()
        ts = self.env['investment.timeseries'].search([
            ('position_id', '=', self.position.id),
            ('date', '=', today),
        ])
        self.assertEqual(len(ts), 1)

    def test_timeseries_today_values(self):
        """Today's timeseries reflects current position values"""
        today = date.today()
        ts = self.env['investment.timeseries'].search([
            ('position_id', '=', self.position.id),
            ('date', '=', today),
        ])
        # quantity = 12, position = 12*100 = 1200, investment = 1025, profit = 175
        self.assertAlmostEqual(ts.quantity, 12.0)
        self.assertAlmostEqual(ts.position, 1200.0, places=0)
        self.assertAlmostEqual(ts.profit, 175.0, places=0)

    def test_granularity_daily(self):
        """Regular date is classified as daily"""
        # Pick a date that's not end of month/quarter/year
        ts = self.env['investment.timeseries'].search([
            ('position_id', '=', self.position.id),
            ('granularity', '=', '4_daily'),
        ], limit=1)
        if ts:
            d = ts.date
            # Verify it's not end of month
            from odoo.tools import date_utils
            self.assertNotEqual(d, date_utils.end_of(d, "month"))

    def test_granularity_monthly(self):
        """Last day of month is classified as monthly or higher"""
        from odoo.tools import date_utils
        all_ts = self.env['investment.timeseries'].search([
            ('position_id', '=', self.position.id),
        ])
        for ts in all_ts:
            if ts.date == date_utils.end_of(ts.date, "month") and ts.date != date_utils.end_of(ts.date, "quarter"):
                self.assertEqual(ts.granularity, '3_monthly')
                break

    def test_is_sunday(self):
        """is_sunday correctly identifies Sundays"""
        all_ts = self.env['investment.timeseries'].search([
            ('position_id', '=', self.position.id),
        ])
        for ts in all_ts:
            if ts.date.isoweekday() == 7:
                self.assertTrue(ts.is_sunday)
            else:
                self.assertFalse(ts.is_sunday)

    def test_timeseries_before_first_transaction(self):
        """No timeseries records before first transaction"""
        first_tx = self.env['investment.position.transaction'].search([
            ('position_id', '=', self.position.id),
        ], order='time asc', limit=1)
        earlier = self.env['investment.timeseries'].search([
            ('position_id', '=', self.position.id),
            ('date', '<', first_tx.time.date()),
        ])
        self.assertEqual(len(earlier), 0)

    def test_timeseries_at_buy1_date(self):
        """Timeseries at buy1 date shows correct quantity"""
        buy_date = self.tx_buy1.time.date()
        ts = self.env['investment.timeseries'].search([
            ('position_id', '=', self.position.id),
            ('date', '=', buy_date),
        ])
        if ts:
            # On buy1 date, only buy1 exists: qty=10
            self.assertAlmostEqual(ts.quantity, 10.0)

    def test_timeseries_open_high_low_follow_intraday_prices(self):
        day = date(2024, 6, 10)
        asset = self.env['investment.asset'].create({
            'ticker': 'TS-INTRADAY',
            'category_id': self.category.id,
            'currency_id': self.currency_eur.id,
        })
        position = self.env['investment.position'].create({
            'name': 'Intraday Position',
            'asset_id': asset.id,
            'portfolio_id': self.portfolio.id,
            'company_id': self.company.id,
        })

        self.env['investment.position.transaction'].create({
            'position_id': position.id,
            'quantity': 2.0,
            'exchange_rate': 100.0,
            'payment': 200.0,
            'time': datetime(2024, 6, 9, 18, 0, 0),
        })
        self.env['investment.position.transaction'].create({
            'position_id': position.id,
            'quantity': 3.0,
            'exchange_rate': 110.0,
            'payment': 330.0,
            'time': datetime(2024, 6, 10, 11, 0, 0),
        })
        self.env['investment.position.transaction'].create({
            'position_id': position.id,
            'quantity': -1.0,
            'exchange_rate': 150.0,
            'payment': 150.0,
            'time': datetime(2024, 6, 10, 13, 0, 0),
        })

        open_price = self.env['investment.asset.price'].create({
            'asset_id': asset.id,
            'time': datetime(2024, 6, 10, 10, 0, 0),
            'price': 100.0,
        })
        high_price = self.env['investment.asset.price'].create({
            'asset_id': asset.id,
            'time': datetime(2024, 6, 10, 12, 0, 0),
            'price': 150.0,
        })
        low_price = self.env['investment.asset.price'].create({
            'asset_id': asset.id,
            'time': datetime(2024, 6, 10, 15, 0, 0),
            'price': 90.0,
        })
        close_price = self.env['investment.asset.price'].create({
            'asset_id': asset.id,
            'time': datetime(2024, 6, 10, 18, 0, 0),
            'price': 120.0,
        })
        asset.last_price_id = close_price

        ts = self.env['investment.timeseries'].create({
            'position_id': position.id,
            'price_id': close_price.id,
            'date': day,
        })
        ts._compute_timeseries_aggregate()

        self.assertEqual(ts.open_price_id, open_price)
        self.assertEqual(ts.high_price_id, high_price)
        self.assertEqual(ts.low_price_id, low_price)
        self.assertAlmostEqual(ts.open_position, 200.0)
        self.assertAlmostEqual(ts.open_profit, 0.0)
        self.assertAlmostEqual(ts.high_position, 750.0)
        self.assertAlmostEqual(ts.high_profit, 220.0)
        self.assertAlmostEqual(ts.low_position, 360.0)
        self.assertAlmostEqual(ts.low_profit, -20.0)

    def test_timeseries_open_high_low_fall_back_to_closing_price(self):
        day = date(2024, 6, 11)
        asset = self.env['investment.asset'].create({
            'ticker': 'TS-FALLBACK',
            'category_id': self.category.id,
            'currency_id': self.currency_eur.id,
        })
        position = self.env['investment.position'].create({
            'name': 'Fallback Position',
            'asset_id': asset.id,
            'portfolio_id': self.portfolio.id,
            'company_id': self.company.id,
        })

        self.env['investment.position.transaction'].create({
            'position_id': position.id,
            'quantity': 2.0,
            'exchange_rate': 40.0,
            'payment': 80.0,
            'time': datetime(2024, 6, 10, 9, 0, 0),
        })
        self.env['investment.position.transaction'].create({
            'position_id': position.id,
            'quantity': 1.0,
            'exchange_rate': 45.0,
            'payment': 45.0,
            'time': datetime(2024, 6, 11, 12, 0, 0),
        })

        close_price = self.env['investment.asset.price'].create({
            'asset_id': asset.id,
            'time': datetime(2024, 6, 10, 18, 0, 0),
            'price': 50.0,
        })
        asset.last_price_id = close_price

        ts = self.env['investment.timeseries'].create({
            'position_id': position.id,
            'price_id': close_price.id,
            'date': day,
        })
        ts._compute_timeseries_aggregate()

        self.assertEqual(ts.open_price_id, close_price)
        self.assertEqual(ts.high_price_id, close_price)
        self.assertEqual(ts.low_price_id, close_price)
        self.assertAlmostEqual(ts.open_position, ts.position)
        self.assertAlmostEqual(ts.open_profit, ts.profit)
        self.assertAlmostEqual(ts.high_position, ts.position)
        self.assertAlmostEqual(ts.high_profit, ts.profit)
        self.assertAlmostEqual(ts.low_position, ts.position)
        self.assertAlmostEqual(ts.low_profit, ts.profit)
