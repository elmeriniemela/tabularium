# -*- coding: utf-8 -*-

from odoo.tests import tagged
from .common import InvestmentTestCommon
from datetime import datetime, timedelta


@tagged('post_install', '-at_install')
class TestAssetAdvanced(InvestmentTestCommon):

    def test_ath_drawdown_calculation(self):
        """current_ath_drawdown = (ath - last) / ath"""
        # ATH is 100 (price_recent), last_price is also 100
        self.asset._compute_ath_price()
        # At ATH: drawdown should be 0
        self.assertAlmostEqual(self.asset.current_ath_drawdown, 0.0, places=2)

    def test_ath_drawdown_below_ath(self):
        """When last price is below ATH, drawdown is positive"""
        # Create a higher historical price to be the ATH
        now = datetime.now()
        self.env['investment.asset.price'].create({
            'asset_id': self.asset.id,
            'time': now - timedelta(days=45),
            'price': 120.0,
        })
        self.asset._compute_ath_price()
        # ATH = 120, last = 100, drawdown = (120 - 100) / 120 = 0.1667
        self.assertAlmostEqual(self.asset.ath_price, 120.0, places=2)
        self.assertAlmostEqual(self.asset.current_ath_drawdown, 20.0 / 120.0, places=4)

    def test_drawdown_price_calculation(self):
        """drawdown_price = (1 - plausible_ath_drawdown) * ath_price"""
        self.asset._compute_ath_price()
        # plausible_ath_drawdown = 0.30, ath = 100
        # drawdown_price = (1 - 0.30) * 100 = 70
        self.assertAlmostEqual(self.asset.drawdown_price, 70.0, places=2)

    def test_price_percent_change_daily(self):
        """daily_price = (last - daily_ref) / daily_ref"""
        # Set daily_price_id to price_mid (95)
        self.asset.daily_price_id = self.price_mid
        self.asset._compute_last_price()
        # (100 - 95) / 95 = 0.05263
        expected = (100.0 - 95.0) / 95.0
        self.assertAlmostEqual(self.asset.daily_price, expected, places=4)

    def test_price_percent_change_weekly(self):
        """weekly_price = (last - weekly_ref) / weekly_ref"""
        self.asset.weekly_price_id = self.price_old
        self.asset._compute_last_price()
        # (100 - 90) / 90 = 0.1111
        expected = (100.0 - 90.0) / 90.0
        self.assertAlmostEqual(self.asset.weekly_price, expected, places=4)

    def test_price_percent_change_no_reference(self):
        """When reference price is empty, percent change is 0"""
        self.asset.daily_price_id = False
        self.asset._compute_last_price()
        self.assertAlmostEqual(self.asset.daily_price, 0.0, places=4)

    def test_inverse_last_price_creates_new(self):
        """Setting last_price when no record exists creates a new price"""
        asset2 = self.env['investment.asset'].create({
            'ticker': 'NEW-ASSET',
            'category_id': self.category.id,
            'currency_id': self.currency_eur.id,
        })
        asset2.last_price = 55.0
        self.assertTrue(asset2.last_price_id)
        self.assertAlmostEqual(asset2.last_price_id.price, 55.0, places=2)

    def test_inverse_last_price_updates_same_day(self):
        """Setting last_price on same day updates existing record"""
        old_price_id = self.asset.last_price_id.id
        self.asset.last_price = 105.0
        # Should update the same record (same day)
        self.assertEqual(self.asset.last_price_id.id, old_price_id)
        self.assertAlmostEqual(self.asset.last_price, 105.0, places=2)

    def test_multiple_splits_price_adjusted(self):
        """Multiple splits compound on price adjustment"""
        now = datetime.now()
        # First split at -20 days, factor 2
        split_price1 = self.env['investment.asset.price'].create({
            'asset_id': self.asset.id,
            'time': now - timedelta(days=20),
            'price': 50.0,
        })
        self.env['investment.asset.split'].create({
            'price_id': split_price1.id,
            'factor': 2.0,
        })
        # Second split at -10 days, factor 3
        split_price2 = self.env['investment.asset.price'].create({
            'asset_id': self.asset.id,
            'time': now - timedelta(days=10),
            'price': 25.0,
        })
        self.env['investment.asset.split'].create({
            'price_id': split_price2.id,
            'factor': 3.0,
        })
        # price_old (90 @ -60d) is before both splits: adjusted = 90 / 2 / 3 = 15
        self.price_old.invalidate_recordset(['price_adjusted'])
        self.assertAlmostEqual(self.price_old.price_adjusted, 15.0, places=2)

    def test_split_price_adjusted_after_split(self):
        """Price after all splits is not adjusted"""
        now = datetime.now()
        split_price = self.env['investment.asset.price'].create({
            'asset_id': self.asset.id,
            'time': now - timedelta(days=45),
            'price': 50.0,
        })
        self.env['investment.asset.split'].create({
            'price_id': split_price.id,
            'factor': 2.0,
        })
        # price_recent is after the split, no adjustment
        self.price_recent.invalidate_recordset(['price_adjusted'])
        self.assertAlmostEqual(self.price_recent.price_adjusted, 100.0, places=2)

    def test_prediction_price_specific_value(self):
        """Prediction: price * (1 + appreciation)^(days/365)"""
        future_date = (datetime.now() + timedelta(days=365)).date()
        result = self.asset.price_at_date(future_date)
        # 100 * (1 + 0.10)^(365/365) = 110.0
        self.assertAlmostEqual(result.price, 110.0, places=0)
        self.assertTrue(result.prediction)

    def test_interpolation_quarter_point(self):
        """Linear interpolation at quarter point between two prices"""
        # price_old: 90 @ -60d, price_mid: 95 @ -30d
        quarter_date = (self.price_old.time + timedelta(days=7.5)).date()
        result = self.asset.price_at_date(quarter_date)
        # 90 + (95-90)*(7.5/30) = 90 + 1.25 = 91.25
        self.assertAlmostEqual(result.price, 91.25, places=0)

    def test_position_count(self):
        """position_count correctly counts positions for this asset"""
        self.asset._compute_position_count()
        self.assertGreaterEqual(self.asset.position_count, 1)

    def test_price_display_name(self):
        """Display name is '{price} @ {time}'"""
        self.price_recent.invalidate_recordset(['display_name'])
        self.assertIn('100', self.price_recent.display_name)
        self.assertIn('@', self.price_recent.display_name)

    def test_price_date_computed(self):
        """Date is extracted from time"""
        expected_date = self.price_recent.time.date()
        self.assertEqual(self.price_recent.date, expected_date)
