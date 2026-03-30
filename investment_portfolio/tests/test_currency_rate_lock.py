# -*- coding: utf-8 -*-

from datetime import date, datetime

from odoo.exceptions import ValidationError
from odoo.tests import tagged, TransactionCase


@tagged('post_install', '-at_install')
class TestCurrencyRateLock(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.currency_usd = cls.env.ref('base.USD')
        cls.category = cls.env['investment.category'].create({
            'name': 'Currency Relation Test Category',
        })
        cls.asset = cls.env['investment.asset'].create({
            'ticker': 'CURR-LINK',
            'category_id': cls.category.id,
            'currency_id': cls.env.ref('base.EUR').id,
        })

    def _create_company(self):
        company = self.env['res.company'].create({
            'name': 'Currency Rate Lock Test Company',
        })
        company.partner_id.tz = 'UTC'
        return company

    def _create_rate(self, company, rate_date=date(2025, 1, 2)):
        return self.env['res.currency.rate'].create({
            'name': rate_date,
            'currency_id': self.currency_usd.id,
            'company_id': company.id,
            'rate': 1.1,
        })

    def test_currency_asset_relation(self):
        self.currency_usd.asset_id = self.asset
        self.assertEqual(self.currency_usd.asset_id, self.asset)

    def test_create_blocked_before_lock_time(self):
        company = self._create_company()
        company.investment_lock_time = datetime(2025, 1, 3, 0, 0, 0)

        with self.assertRaises(ValidationError):
            self._create_rate(company)

    def test_write_blocked_before_lock_time(self):
        company = self._create_company()
        rate = self._create_rate(company)
        self.assertFalse(rate.is_locked)
        company.investment_lock_time = datetime(2025, 1, 3, 0, 0, 0)
        self.assertTrue(rate.is_locked)

        with self.assertRaises(ValidationError):
            rate.write({'rate': 1.2})

    def test_unlink_blocked_before_lock_time(self):
        company = self._create_company()
        rate = self._create_rate(company)
        self.assertFalse(rate.is_locked)
        company.investment_lock_time = datetime(2025, 1, 3, 0, 0, 0)
        self.assertTrue(rate.is_locked)

        with self.assertRaises(ValidationError):
            rate.unlink()

    def test_is_locked_computed(self):
        company = self._create_company()
        rate = self._create_rate(company)
        self.assertFalse(rate.is_locked)

        company.investment_lock_time = datetime(2025, 1, 3, 0, 0, 0)
        self.assertTrue(rate.is_locked)

        company.investment_lock_time = datetime(2025, 1, 1, 0, 0, 0)
        self.assertFalse(rate.is_locked)
