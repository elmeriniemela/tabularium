# -*- coding: utf-8 -*-

from odoo.tests import tagged, TransactionCase
from datetime import datetime, timedelta


@tagged('post_install', '-at_install')
class InvestmentTestCommon(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.company = cls.env.company
        cls.currency_eur = cls.env.ref('base.EUR')
        cls.company.currency_id = cls.currency_eur

        cls.category = cls.env['investment.category'].create({
            'name': 'Stocks',
            'liquid': True,
        })

        cls.portfolio = cls.env['investment.portfolio'].create({
            'name': 'Test Portfolio',
        })

        cls.asset = cls.env['investment.asset'].create({
            'ticker': 'TEST-EUR',
            'category_id': cls.category.id,
            'currency_id': cls.currency_eur.id,
            'expected_yearly_appreciation': 0.10,
            'plausible_ath_drawdown': 0.30,
        })

        # Create price records
        now = datetime.now()
        cls.price_old = cls.env['investment.asset.price'].create({
            'asset_id': cls.asset.id,
            'time': now - timedelta(days=60),
            'price': 90.0,
        })
        cls.price_mid = cls.env['investment.asset.price'].create({
            'asset_id': cls.asset.id,
            'time': now - timedelta(days=30),
            'price': 95.0,
        })
        cls.price_recent = cls.env['investment.asset.price'].create({
            'asset_id': cls.asset.id,
            'time': now - timedelta(hours=1),
            'price': 100.0,
        })

        cls.asset.last_price_id = cls.price_recent

        cls.position = cls.env['investment.position'].create({
            'name': 'Test Position',
            'asset_id': cls.asset.id,
            'portfolio_id': cls.portfolio.id,
            'company_id': cls.company.id,
        })

        # Buy 10 units @ 90
        cls.tx_buy1 = cls.env['investment.position.transaction'].create({
            'position_id': cls.position.id,
            'quantity': 10.0,
            'exchange_rate': 90.0,
            'payment': 900.0,
            'time': now - timedelta(days=60),
        })

        # Buy 5 units @ 95
        cls.tx_buy2 = cls.env['investment.position.transaction'].create({
            'position_id': cls.position.id,
            'quantity': 5.0,
            'exchange_rate': 95.0,
            'payment': 475.0,
            'time': now - timedelta(days=30),
        })

        # Sell 3 units @ 100
        cls.tx_sell1 = cls.env['investment.position.transaction'].create({
            'position_id': cls.position.id,
            'quantity': -3.0,
            'exchange_rate': 100.0,
            'payment': 300.0,
            'time': now - timedelta(days=10),
        })

        # Yield 50 EUR
        cls.tx_yield1 = cls.env['investment.position.transaction'].create({
            'position_id': cls.position.id,
            'quantity': 0.0,
            'exchange_rate': 0.0,
            'payment': 50.0,
            'time': now - timedelta(days=5),
        })
