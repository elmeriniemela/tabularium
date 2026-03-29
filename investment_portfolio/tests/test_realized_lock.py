# -*- coding: utf-8 -*-

from datetime import datetime

from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .common import InvestmentTestCommon


@tagged('post_install', '-at_install')
class TestRealizedLock(InvestmentTestCommon):

    def _create_buy_sell_pair(self):
        company = self.env['res.company'].create({
            'name': 'Realized Lock Test Company',
        })
        company.partner_id.tz = 'UTC'
        position = self.env['investment.position'].create({
            'name': 'Realized Lock Test',
            'asset_id': self.asset.id,
            'portfolio_id': self.portfolio.id,
            'company_id': company.id,
            'compute_realized': False,
        })
        buy = self.env['investment.position.transaction'].create({
            'position_id': position.id,
            'quantity': 2.0,
            'exchange_rate': 50.0,
            'payment': 100.0,
            'time': datetime(2025, 1, 1, 12, 0, 0),
        })
        sell = self.env['investment.position.transaction'].create({
            'position_id': position.id,
            'quantity': -1.0,
            'exchange_rate': 60.0,
            'payment': 60.0,
            'time': datetime(2025, 1, 2, 12, 0, 0),
        })
        position._compute_position_aggregate()
        return company, position, buy, sell

    def test_create_blocked_before_lock_time(self):
        company, position, buy, sell = self._create_buy_sell_pair()
        company.investment_lock_time = datetime(2025, 1, 3, 0, 0, 0)

        with self.assertRaises(ValidationError):
            self.env['investment.asset.realized'].create({
                'position_id': position.id,
                'buy_batch_id': buy.id,
                'sell_batch_id': sell.id,
                'quantity': 1.0,
            })

    def test_write_blocked_before_lock_time(self):
        company, position, buy, sell = self._create_buy_sell_pair()
        realized = self.env['investment.asset.realized'].create({
            'position_id': position.id,
            'buy_batch_id': buy.id,
            'sell_batch_id': sell.id,
            'quantity': 1.0,
        })
        self.assertFalse(realized.is_locked)
        company.investment_lock_time = datetime(2025, 1, 3, 0, 0, 0)
        self.assertTrue(realized.is_locked)

        with self.assertRaises(ValidationError):
            realized.write({'quantity': 2.0})

    def test_unlink_blocked_before_lock_time(self):
        company, position, buy, sell = self._create_buy_sell_pair()
        realized = self.env['investment.asset.realized'].create({
            'position_id': position.id,
            'buy_batch_id': buy.id,
            'sell_batch_id': sell.id,
            'quantity': 1.0,
        })
        self.assertFalse(realized.is_locked)
        company.investment_lock_time = datetime(2025, 1, 3, 0, 0, 0)
        self.assertTrue(realized.is_locked)

        with self.assertRaises(ValidationError):
            realized.unlink()

    def test_is_locked_computed(self):
        company, position, buy, sell = self._create_buy_sell_pair()
        realized = self.env['investment.asset.realized'].create({
            'position_id': position.id,
            'buy_batch_id': buy.id,
            'sell_batch_id': sell.id,
            'quantity': 1.0,
        })
        self.assertFalse(realized.is_locked)

        company.investment_lock_time = datetime(2025, 1, 3, 0, 0, 0)
        self.assertTrue(realized.is_locked)

        company.investment_lock_time = datetime(2025, 1, 1, 0, 0, 0)
        self.assertFalse(realized.is_locked)
