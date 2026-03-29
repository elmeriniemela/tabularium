# -*- coding: utf-8 -*-

from datetime import datetime

from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .common import InvestmentTestCommon


@tagged('post_install', '-at_install')
class TestTransactionLock(InvestmentTestCommon):

    def _create_company_position(self):
        company = self.env['res.company'].create({
            'name': 'Transaction Lock Test Company',
        })
        company.partner_id.tz = 'UTC'
        position = self.env['investment.position'].create({
            'name': 'Transaction Lock Test Position',
            'asset_id': self.asset.id,
            'portfolio_id': self.portfolio.id,
            'company_id': company.id,
            'compute_realized': False,
        })
        return company, position

    def test_create_blocked_before_lock_time(self):
        company, position = self._create_company_position()
        company.investment_lock_time = datetime(2025, 1, 3, 0, 0, 0)

        with self.assertRaises(ValidationError):
            self.env['investment.position.transaction'].create({
                'position_id': position.id,
                'quantity': 1.0,
                'exchange_rate': 50.0,
                'payment': 50.0,
                'time': datetime(2025, 1, 2, 12, 0, 0),
            })

    def test_write_blocked_before_lock_time(self):
        company, position = self._create_company_position()
        tx = self.env['investment.position.transaction'].create({
            'position_id': position.id,
            'quantity': 1.0,
            'exchange_rate': 50.0,
            'payment': 50.0,
            'time': datetime(2025, 1, 2, 12, 0, 0),
        })
        self.assertFalse(tx.is_locked)
        company.investment_lock_time = datetime(2025, 1, 3, 0, 0, 0)
        self.assertTrue(tx.is_locked)

        with self.assertRaises(ValidationError):
            tx.write({'quantity': 2.0})

    def test_unlink_blocked_before_lock_time(self):
        company, position = self._create_company_position()
        tx = self.env['investment.position.transaction'].create({
            'position_id': position.id,
            'quantity': 1.0,
            'exchange_rate': 50.0,
            'payment': 50.0,
            'time': datetime(2025, 1, 2, 12, 0, 0),
        })
        self.assertFalse(tx.is_locked)
        company.investment_lock_time = datetime(2025, 1, 3, 0, 0, 0)
        self.assertTrue(tx.is_locked)

        with self.assertRaises(ValidationError):
            tx.unlink()

    def test_is_locked_computed(self):
        company, position = self._create_company_position()
        tx = self.env['investment.position.transaction'].create({
            'position_id': position.id,
            'quantity': 1.0,
            'exchange_rate': 50.0,
            'payment': 50.0,
            'time': datetime(2025, 1, 2, 12, 0, 0),
        })
        self.assertFalse(tx.is_locked)

        company.investment_lock_time = datetime(2025, 1, 3, 0, 0, 0)
        self.assertTrue(tx.is_locked)

        company.investment_lock_time = datetime(2025, 1, 1, 0, 0, 0)
        self.assertFalse(tx.is_locked)
