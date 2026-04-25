# -*- coding: utf-8 -*-

from datetime import datetime, timedelta

from odoo.tests import tagged

from .common import InvestmentTestCommon


@tagged('post_install', '-at_install')
class TestTotalTimeseries(InvestmentTestCommon):

    def _expected_times(self, day):
        return [
            datetime(day.year, day.month, day.day, 0, 0, 0),
            datetime(day.year, day.month, day.day, 0, 0, 1),
            datetime(day.year, day.month, day.day, 0, 0, 2),
            datetime(day.year, day.month, day.day, 0, 0, 3),
        ]

    def _create_source_series(self, day, rows, *, company=None, liquid=True, prediction=False):
        company = company or self.env['res.company'].browse(1)
        category = self.category
        if not liquid:
            category = self.env['investment.category'].create({
                'name': f'Illiquid {day:%Y%m%d}',
                'liquid': False,
            })
        for index, (open_position, high_position, low_position, close_position) in enumerate(rows, start=1):
            asset = self.env['investment.asset'].create({
                'ticker': f'TOTAL-SQL-{day:%Y%m%d}-{index}-{company.id}-{int(liquid)}-{int(prediction)}',
                'category_id': category.id,
                'currency_id': self.currency_eur.id,
            })
            position = self.env['investment.position'].create({
                'name': f'Total SQL {day:%Y%m%d} {index}',
                'asset_id': asset.id,
                'portfolio_id': self.portfolio.id,
                'company_id': company.id,
            })
            price = self.env['investment.asset.price'].create({
                'asset_id': asset.id,
                'time': datetime(day.year, day.month, day.day, 18, 0, 0),
                'price': 1.0,
                'prediction': prediction,
            })
            series = self.env['investment.timeseries'].create({
                'position_id': position.id,
                'date': day.date(),
                'price_id': price.id,
            })
            self.env.cr.execute("""
                UPDATE investment_timeseries
                SET
                    open_position = %s,
                    high_position = %s,
                    low_position = %s,
                    position = %s
                WHERE id = %s
            """, [open_position, high_position, low_position, close_position, series.id])

    def _get_day_lines(self, day):
        start = datetime(day.year, day.month, day.day, 0, 0, 0)
        stop = start + timedelta(days=1)
        return self.env['investment.total.timeseries'].search([
            ('time', '>=', start),
            ('time', '<', stop),
        ], order='time asc, id asc')

    def test_total_timeseries_returns_daily_ohlc(self):
        day = datetime(2024, 6, 10, 0, 0, 0)
        self._create_source_series(day, [
            (1100.0, 1200.0, 900.0, 900.0),
            (220.0, 240.0, 180.0, 180.0),
            (200.0, 280.0, 200.0, 280.0),
        ])

        lines = self._get_day_lines(day)
        self.assertEqual([
            (self._expected_times(day)[0], 1520.0),
            (self._expected_times(day)[1], 1720.0),
            (self._expected_times(day)[2], 1280.0),
            (self._expected_times(day)[3], 1360.0),
        ], [(line.time, line.position) for line in lines])

    def test_total_timeseries_applies_quantity_changes_between_prices(self):
        day = datetime(2024, 6, 11, 0, 0, 0)
        self._create_source_series(day, [
            (100.0, 150.0, 90.0, 140.0),
            (300.0, 350.0, 310.0, 360.0),
        ])

        lines = self._get_day_lines(day)
        self.assertEqual([
            (self._expected_times(day)[0], 400.0),
            (self._expected_times(day)[1], 500.0),
            (self._expected_times(day)[2], 400.0),
            (self._expected_times(day)[3], 500.0),
        ], [(line.time, line.position) for line in lines])

    def test_total_timeseries_keeps_days_separate(self):
        first_day = datetime(2024, 6, 12, 0, 0, 0)
        second_day = datetime(2024, 6, 13, 0, 0, 0)
        self._create_source_series(first_day, [
            (500.0, 600.0, 450.0, 550.0),
        ])
        self._create_source_series(second_day, [
            (50.0, 70.0, 40.0, 60.0),
            (150.0, 180.0, 140.0, 160.0),
        ])

        self.assertEqual([
            (self._expected_times(first_day)[0], 500.0),
            (self._expected_times(first_day)[1], 600.0),
            (self._expected_times(first_day)[2], 450.0),
            (self._expected_times(first_day)[3], 550.0),
        ], [(line.time, line.position) for line in self._get_day_lines(first_day)])
        self.assertEqual([
            (self._expected_times(second_day)[0], 200.0),
            (self._expected_times(second_day)[1], 250.0),
            (self._expected_times(second_day)[2], 180.0),
            (self._expected_times(second_day)[3], 220.0),
        ], [(line.time, line.position) for line in self._get_day_lines(second_day)])

    def test_total_timeseries_filters_company_liquid_and_prediction(self):
        day = datetime(2024, 6, 14, 0, 0, 0)
        other_company = self.env['res.company'].create({'name': 'Other Company'})

        self._create_source_series(day, [
            (100.0, 110.0, 90.0, 105.0),
        ])
        self._create_source_series(day, [
            (500.0, 550.0, 450.0, 525.0),
        ], company=other_company)
        self._create_source_series(day, [
            (700.0, 710.0, 690.0, 705.0),
        ], liquid=False)
        self._create_source_series(day, [
            (900.0, 950.0, 850.0, 925.0),
        ], prediction=True)

        lines = self._get_day_lines(day)
        self.assertEqual([
            (self._expected_times(day)[0], 100.0),
            (self._expected_times(day)[1], 110.0),
            (self._expected_times(day)[2], 90.0),
            (self._expected_times(day)[3], 105.0),
        ], [(line.time, line.position) for line in lines])
