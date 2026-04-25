# -*- coding: utf-8 -*-

from odoo.tests import tagged
from .common import InvestmentTestCommon
from datetime import datetime, timedelta
import pytz


@tagged('post_install', '-at_install')
class TestAsset(InvestmentTestCommon):

    def test_price_at_date_exact(self):
        """Exact date match returns correct price"""
        date = self.price_mid.time.date()
        result = self.asset.closing_price_utc(date)
        self.assertAlmostEqual(result.price, 95.0, places=2)

    def test_price_at_date_interpolation(self):
        """Linear interpolation between two known prices"""
        # Midpoint between price_old (90 @ -60d) and price_mid (95 @ -30d)
        mid_date = (self.price_old.time + timedelta(days=15)).date()
        result = self.asset.closing_price_utc(mid_date)
        # Linear interpolation: 90 + (95-90)*(15/30) = 92.5
        self.assertAlmostEqual(result.price, 92.5, places=0)

    def test_price_at_date_prediction(self):
        """Forward prediction using expected_yearly_appreciation"""
        # Price beyond last known price should use appreciation
        future_date = (datetime.now() + timedelta(days=365)).date()
        result = self.asset.closing_price_utc(future_date)
        # predicted = 100 * (1 + 0.10)^(days/365) ~ 110
        self.assertGreater(result.price, 100.0)
        self.assertTrue(result.prediction)

    def test_price_at_date_no_prices(self):
        """Raises RuntimeError when no prices exist"""
        empty_asset = self.env['investment.asset'].create({
            'ticker': 'EMPTY',
            'category_id': self.category.id,
            'currency_id': self.currency_eur.id,
        })
        with self.assertRaises(RuntimeError):
            empty_asset.closing_price_utc(datetime.now().date())

    def test_price_upsert_create(self):
        """Creates new price record"""
        time = datetime.now().replace(second=0, microsecond=0) - timedelta(days=100)
        time_aware = pytz.utc.localize(time)
        self.asset.price_upsert(time_aware, 85.0)
        price = self.env['investment.asset.price'].search([
            ('asset_id', '=', self.asset.id),
            ('time', '=', time),
        ])
        self.assertEqual(len(price), 1)
        self.assertAlmostEqual(price.price, 85.0, places=2)

    def test_price_upsert_update(self):
        """Updates existing price at same time"""
        time = self.price_mid.time
        time_aware = pytz.utc.localize(time)
        self.asset.price_upsert(time_aware, 99.0)
        self.price_mid.invalidate_recordset(['price'])
        self.assertAlmostEqual(self.price_mid.price, 99.0, places=2)

    def test_price_adjusted_with_split(self):
        """Price before split is divided by split factor"""
        now = datetime.now()
        split_price = self.env['investment.asset.price'].create({
            'asset_id': self.asset.id,
            'time': now - timedelta(days=15),
            'price': 50.0,
        })
        self.env['investment.asset.split'].create({
            'price_id': split_price.id,
            'factor': 2.0,
        })
        # price_old (90 @ -60d) is before the split at -15d, adjusted = 90/2 = 45
        self.price_old.invalidate_recordset(['price_adjusted'])
        self.assertAlmostEqual(self.price_old.price_adjusted, 45.0, places=2)

    def test_ath_price_computation(self):
        """All-time high tracks maximum price_adjusted"""
        self.asset._compute_ath_price()
        self.assertAlmostEqual(self.asset.ath_price, 100.0, places=2)
