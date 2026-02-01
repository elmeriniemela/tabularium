# -*- coding: utf-8 -*-

from odoo.tests import tagged, TransactionCase
from odoo.addons.investment_portfolio.models.investment_position import banking_date
from datetime import date


@tagged('post_install', '-at_install')
class TestHelpers(TransactionCase):

    def test_banking_date_weekday(self):
        """15th on a Wednesday returns 15th"""
        # 2025-01-15 is a Wednesday
        d = date(2025, 1, 15)
        result = banking_date(d)
        self.assertEqual(result, date(2025, 1, 15))

    def test_banking_date_saturday(self):
        """When 15th is Saturday, returns Monday 17th"""
        # 2025-02-15 is a Saturday
        d = date(2025, 2, 1)  # any date in Feb 2025; banking_date replaces day=15
        result = banking_date(d)
        # Feb 15, 2025 is Saturday => Monday = Feb 17
        self.assertEqual(result, date(2025, 2, 17))

    def test_banking_date_sunday(self):
        """When 15th is Sunday, returns Monday 16th"""
        # 2025-06-15 is a Sunday
        d = date(2025, 6, 1)
        result = banking_date(d)
        # June 15, 2025 is Sunday => Monday = June 16
        self.assertEqual(result, date(2025, 6, 16))
