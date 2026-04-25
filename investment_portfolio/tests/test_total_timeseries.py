# -*- coding: utf-8 -*-

from datetime import datetime, timedelta

from odoo.tests import tagged

from .common import InvestmentTestCommon


@tagged('post_install', '-at_install')
class TestTotalTimeseries(InvestmentTestCommon):

    def _get_day_lines(self, day):
        start = datetime(day.year, day.month, day.day, 0, 0, 0)
        stop = start + timedelta(days=1)
        return self.env['investment.total.timeseries'].search([
            ('time', '>=', start),
            ('time', '<', stop),
        ], order='time asc, id asc')

    def test_total_timeseries_returns_daily_ohlc(self):
        day = datetime(2024, 6, 10, 0, 0, 0)
        asset = self.env['investment.asset'].create({
            'ticker': 'TOTAL-SQL',
            'category_id': self.category.id,
            'currency_id': self.currency_eur.id,
        })
        other_asset = self.env['investment.asset'].create({
            'ticker': 'TOTAL-SQL-OTHER',
            'category_id': self.category.id,
            'currency_id': self.currency_eur.id,
        })
        position_one = self.env['investment.position'].create({
            'name': 'Total SQL One',
            'asset_id': asset.id,
            'portfolio_id': self.portfolio.id,
            'company_id': self.company.id,
        })
        position_two = self.env['investment.position'].create({
            'name': 'Total SQL Two',
            'asset_id': asset.id,
            'portfolio_id': self.portfolio.id,
            'company_id': self.company.id,
        })
        other_position = self.env['investment.position'].create({
            'name': 'Total SQL Other',
            'asset_id': other_asset.id,
            'portfolio_id': self.portfolio.id,
            'company_id': self.company.id,
        })

        self.env['investment.position.transaction'].create({
            'position_id': position_one.id,
            'quantity': 10.0,
            'exchange_rate': 90.0,
            'payment': 900.0,
            'time': datetime(2024, 6, 9, 9, 0, 0),
        })
        self.env['investment.position.transaction'].create({
            'position_id': position_two.id,
            'quantity': 2.0,
            'exchange_rate': 95.0,
            'payment': 190.0,
            'time': datetime(2024, 6, 9, 10, 0, 0),
        })
        self.env['investment.position.transaction'].create({
            'position_id': other_position.id,
            'quantity': 4.0,
            'exchange_rate': 45.0,
            'payment': 180.0,
            'time': datetime(2024, 6, 9, 11, 0, 0),
        })

        self.env['investment.asset.price'].create({
            'asset_id': asset.id,
            'time': datetime(2024, 6, 10, 9, 0, 0),
            'price': 110.0,
        })
        self.env['investment.asset.price'].create({
            'asset_id': other_asset.id,
            'time': datetime(2024, 6, 10, 10, 0, 0),
            'price': 50.0,
        })
        self.env['investment.asset.price'].create({
            'asset_id': asset.id,
            'time': datetime(2024, 6, 10, 12, 0, 0),
            'price': 120.0,
        })
        self.env['investment.asset.price'].create({
            'asset_id': asset.id,
            'time': datetime(2024, 6, 10, 15, 0, 0),
            'price': 90.0,
        })
        self.env['investment.asset.price'].create({
            'asset_id': other_asset.id,
            'time': datetime(2024, 6, 10, 18, 0, 0),
            'price': 70.0,
        })

        lines = self._get_day_lines(day)
        self.assertEqual([
            (datetime(2024, 6, 10, 9, 0, 0), 1320.0),
            (datetime(2024, 6, 10, 12, 0, 0), 1640.0),
            (datetime(2024, 6, 10, 15, 0, 0), 1280.0),
            (datetime(2024, 6, 10, 18, 0, 0), 1360.0),
        ], [(line.time, line.position) for line in lines])

    def test_total_timeseries_applies_quantity_changes_between_prices(self):
        day = datetime(2024, 6, 11, 0, 0, 0)
        asset = self.env['investment.asset'].create({
            'ticker': 'TOTAL-SQL-QTY',
            'category_id': self.category.id,
            'currency_id': self.currency_eur.id,
        })
        position = self.env['investment.position'].create({
            'name': 'Total SQL Qty',
            'asset_id': asset.id,
            'portfolio_id': self.portfolio.id,
            'company_id': self.company.id,
        })

        self.env['investment.position.transaction'].create({
            'position_id': position.id,
            'quantity': 4.0,
            'exchange_rate': 100.0,
            'payment': 400.0,
            'time': datetime(2024, 6, 10, 18, 0, 0),
        })
        self.env['investment.position.transaction'].create({
            'position_id': position.id,
            'quantity': 1.0,
            'exchange_rate': 100.0,
            'payment': 100.0,
            'time': datetime(2024, 6, 11, 12, 0, 0),
        })

        self.env['investment.asset.price'].create({
            'asset_id': asset.id,
            'time': datetime(2024, 6, 11, 9, 0, 0),
            'price': 100.0,
        })
        self.env['investment.asset.price'].create({
            'asset_id': asset.id,
            'time': datetime(2024, 6, 11, 15, 0, 0),
            'price': 100.0,
        })

        lines = self._get_day_lines(day)
        self.assertEqual([
            (datetime(2024, 6, 11, 9, 0, 0), 400.0),
            (datetime(2024, 6, 11, 9, 0, 0), 400.0),
            (datetime(2024, 6, 11, 15, 0, 0), 500.0),
            (datetime(2024, 6, 11, 15, 0, 0), 500.0),
        ], [(line.time, line.position) for line in lines])

    def test_total_timeseries_filters_company_liquid_and_predictions(self):
        day = datetime(2024, 6, 12, 0, 0, 0)
        included_asset = self.env['investment.asset'].create({
            'ticker': 'TOTAL-SQL-INCLUDED',
            'category_id': self.category.id,
            'currency_id': self.currency_eur.id,
        })
        included_position = self.env['investment.position'].create({
            'name': 'Total SQL Included',
            'asset_id': included_asset.id,
            'portfolio_id': self.portfolio.id,
            'company_id': self.company.id,
        })
        self.env['investment.position.transaction'].create({
            'position_id': included_position.id,
            'quantity': 5.0,
            'exchange_rate': 80.0,
            'payment': 400.0,
            'time': datetime(2024, 6, 11, 18, 0, 0),
        })
        self.env['investment.position.transaction'].create({
            'position_id': included_position.id,
            'quantity': 1.0,
            'exchange_rate': 120.0,
            'payment': 120.0,
            'time': datetime(2024, 6, 12, 8, 0, 0),
            'usage': 'prediction',
        })
        self.env['investment.position.transaction'].create({
            'position_id': included_position.id,
            'quantity': 99.0,
            'exchange_rate': 0.0,
            'payment': 0.0,
            'time': datetime(2024, 6, 12, 8, 30, 0),
            'usage': 'realized',
        })

        self.env['investment.asset.price'].create({
            'asset_id': included_asset.id,
            'time': datetime(2024, 6, 12, 9, 0, 0),
            'price': 100.0,
        })
        self.env['investment.asset.price'].create({
            'asset_id': included_asset.id,
            'time': datetime(2024, 6, 12, 12, 0, 0),
            'price': 120.0,
        })
        self.env['investment.asset.price'].create({
            'asset_id': included_asset.id,
            'time': datetime(2024, 6, 12, 15, 0, 0),
            'price': 90.0,
        })
        self.env['investment.asset.price'].create({
            'asset_id': included_asset.id,
            'time': datetime(2024, 6, 12, 18, 0, 0),
            'price': 110.0,
        })
        self.env['investment.asset.price'].create({
            'asset_id': included_asset.id,
            'time': datetime(2024, 6, 12, 20, 0, 0),
            'price': 140.0,
            'prediction': True,
        })

        illiquid_category = self.env['investment.category'].create({
            'name': 'Illiquid',
            'liquid': False,
        })
        illiquid_asset = self.env['investment.asset'].create({
            'ticker': 'TOTAL-SQL-ILLIQUID',
            'category_id': illiquid_category.id,
            'currency_id': self.currency_eur.id,
        })
        illiquid_position = self.env['investment.position'].create({
            'name': 'Total SQL Illiquid',
            'asset_id': illiquid_asset.id,
            'portfolio_id': self.portfolio.id,
            'company_id': self.company.id,
        })
        self.env['investment.position.transaction'].create({
            'position_id': illiquid_position.id,
            'quantity': 7.0,
            'exchange_rate': 90.0,
            'payment': 630.0,
            'time': datetime(2024, 6, 11, 17, 0, 0),
        })
        self.env['investment.asset.price'].create({
            'asset_id': illiquid_asset.id,
            'time': datetime(2024, 6, 12, 13, 0, 0),
            'price': 999.0,
        })

        company_2 = self.env['res.company'].create({'name': 'Company Two'})
        other_company_asset = self.env['investment.asset'].create({
            'ticker': 'TOTAL-SQL-COMPANY2',
            'category_id': self.category.id,
            'currency_id': self.currency_eur.id,
        })
        other_company_position = self.env['investment.position'].create({
            'name': 'Total SQL Company Two',
            'asset_id': other_company_asset.id,
            'portfolio_id': self.portfolio.id,
            'company_id': company_2.id,
        })
        self.env['investment.position.transaction'].create({
            'position_id': other_company_position.id,
            'quantity': 3.0,
            'exchange_rate': 70.0,
            'payment': 210.0,
            'time': datetime(2024, 6, 11, 16, 0, 0),
        })
        self.env['investment.asset.price'].create({
            'asset_id': other_company_asset.id,
            'time': datetime(2024, 6, 12, 14, 0, 0),
            'price': 777.0,
        })

        lines = self._get_day_lines(day)
        self.assertEqual([
            (datetime(2024, 6, 12, 9, 0, 0), 500.0),
            (datetime(2024, 6, 12, 12, 0, 0), 600.0),
            (datetime(2024, 6, 12, 15, 0, 0), 450.0),
            (datetime(2024, 6, 12, 18, 0, 0), 550.0),
        ], [(line.time, line.position) for line in lines])
