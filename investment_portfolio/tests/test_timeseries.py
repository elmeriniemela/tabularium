# -*- coding: utf-8 -*-

from odoo.tests import tagged
from .common import InvestmentTestCommon
from datetime import date, timedelta


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
