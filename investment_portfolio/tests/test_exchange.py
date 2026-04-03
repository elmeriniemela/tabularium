# -*- coding: utf-8 -*-

from odoo.tests import tagged, TransactionCase
from datetime import date, datetime, timedelta
from unittest.mock import patch

import pytz


@tagged('post_install', '-at_install')
class TestExchange(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.exchange = cls.env['investment.exchange'].create({
            'name': 'Test Exchange',
            'opening_time': 9.5,    # 9:30
            'closing_time': 16.0,   # 16:00
            'tz': 'US/Eastern',
            'weekend_trading': False,
        })

    def test_exchange_fields(self):
        """Exchange has correct field values"""
        self.assertEqual(self.exchange.name, 'Test Exchange')
        self.assertAlmostEqual(self.exchange.opening_time, 9.5)
        self.assertAlmostEqual(self.exchange.closing_time, 16.0)
        self.assertFalse(self.exchange.weekend_trading)

    def test_next_open_computed(self):
        """next_open is computed and is a datetime"""
        self.exchange._compute_open_close()
        self.assertIsNotNone(self.exchange.next_open)

    def test_next_close_computed(self):
        """next_close is computed and is a datetime"""
        self.exchange._compute_open_close()
        self.assertIsNotNone(self.exchange.next_close)

    def test_is_open_boolean(self):
        """is_open is a boolean value"""
        self.exchange._compute_open_close()
        self.assertIsInstance(self.exchange.is_open, bool)

    def test_exchange_gap(self):
        """Gap creates a closure on specific date"""
        gap = self.env['investment.exchange.gap'].create({
            'exchange_id': self.exchange.id,
            'date': date.today(),
            'name': 'Holiday',
            'closing_time': 0.0,
        })
        self.assertEqual(gap.name, 'Holiday')
        self.assertEqual(gap.date, date.today())

    def test_exchange_gap_closing_datetime(self):
        """Gap closing_datetime is computed from date and closing_time"""
        gap = self.env['investment.exchange.gap'].create({
            'exchange_id': self.exchange.id,
            'date': date(2025, 12, 25),
            'name': 'Christmas',
            'closing_time': 13.0,
        })
        self.assertIsNotNone(gap.closing_datetime)

    def test_exchange_gap_no_closing_time(self):
        """Gap with closing_time=0 means full closure"""
        gap = self.env['investment.exchange.gap'].create({
            'exchange_id': self.exchange.id,
            'date': date(2025, 12, 25),
            'name': 'Christmas Full Close',
            'closing_time': 0.0,
        })
        # closing_datetime should be midnight
        self.assertIsNotNone(gap.closing_datetime)

    def test_weekend_trading_exchange(self):
        """Exchange with weekend_trading=True"""
        crypto = self.env['investment.exchange'].create({
            'name': 'Crypto Exchange',
            'opening_time': 0.0,
            'closing_time': 23.99,
            'tz': 'UTC',
            'weekend_trading': True,
        })
        crypto._compute_open_close()
        self.assertIsNotNone(crypto.next_open)

    def test_weekend_skip_branch_with_patched_now(self):
        eastern = pytz.timezone('US/Eastern')
        with patch(
            'odoo.addons.investment_portfolio.models.investment_exchange.fields.Datetime.now',
            return_value=datetime(2026, 4, 4, 12, 0, 0),
        ):
            self.exchange._compute_open_close()

        next_open_local = pytz.UTC.localize(self.exchange.next_open).astimezone(eastern)
        self.assertEqual(next_open_local.isoweekday(), 1)
