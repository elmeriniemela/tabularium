# -*- coding: utf-8 -*-

from datetime import date, datetime, timedelta

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tools import mute_logger

from .common import InvestmentTestCommon


@tagged('post_install', '-at_install')
class TestFunctionalIntegration(InvestmentTestCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.endpoint_usage_field = cls.env.ref('investment_portfolio.field_investment_asset__endpoint_id')

    def _create_test_endpoint(self, *, name, multi_record=False):
        return self.env['api.endpoint'].create({
            'name': name,
            'usage_field_id': self.endpoint_usage_field.id,
            'direction': 'outbound',
            'role': 'active',
            'comm_method': 'http',
            'http_method': 'get',
            'file_format': 'json',
            'location': f'local://{name.lower().replace(" ", "_")}',
            'auto_code': False,
            'auto_consume': False,
            'auto_commit': False,
            'producer': 'obj = {}',
            'consumer': '',
            'multi_record': multi_record,
        })

    def test_acquire_lock_empty_and_missing_records(self):
        self.assertFalse(self.env['investment.asset'].browse().acquire_lock())
        self.assertFalse(self.env['investment.asset'].browse([99999999]).acquire_lock())

    def test_asset_price_actions_and_asset_links(self):
        split = self.env['investment.asset.split'].create({
            'price_id': self.price_recent.id,
            'factor': 2.0,
        })
        ts = self.env['investment.timeseries'].create({
            'position_id': self.position.id,
            'price_id': self.price_recent.id,
            'date': self.price_recent.time.date(),
        })

        asset2 = self.env['investment.asset'].create({
            'ticker': 'LINKED-ASSET',
            'category_id': self.category.id,
            'currency_id': self.currency_eur.id,
        })
        asset2.daily_price_id = self.price_recent

        self.price_recent._compute_asset_ids()
        self.assertIn(self.asset, self.price_recent.asset_ids)
        self.assertIn(asset2, self.price_recent.asset_ids)

        assets_action = self.price_recent.action_view_assets()
        self.assertEqual(assets_action['type'], 'ir.actions.act_window')
        self.assertEqual(assets_action['domain'], [('id', 'in', self.price_recent.asset_ids.ids)])

        timeseries_action = self.price_recent.action_view_timeseries()
        self.assertEqual(timeseries_action['type'], 'ir.actions.act_window')
        self.assertEqual(timeseries_action['domain'], [('id', 'in', ts.ids)])

        splits_action = self.price_recent.action_view_splits()
        self.assertEqual(splits_action['type'], 'ir.actions.act_window')
        self.assertEqual(splits_action['domain'], [('id', 'in', split.ids)])

    def test_interpolate_cagr_create_and_update(self):
        asset = self.env['investment.asset'].create({
            'ticker': 'CAGR-ASSET',
            'category_id': self.category.id,
            'currency_id': self.currency_eur.id,
        })

        first = self.env['investment.asset.price'].create({
            'asset_id': asset.id,
            'time': datetime(2024, 1, 1, 12, 0, 0),
            'price': 100.0,
        })
        last = self.env['investment.asset.price'].create({
            'asset_id': asset.id,
            'time': datetime(2024, 5, 1, 12, 0, 0),
            'price': 200.0,
        })

        (first + last).interpolate_cagr()
        prices = self.env['investment.asset.price'].search([
            ('asset_id', '=', asset.id),
            ('interpolated', '=', True),
        ])
        self.assertGreaterEqual(len(prices), 1)

        feb_price = self.env['investment.asset.price'].search([
            ('asset_id', '=', asset.id),
            ('time', '=', datetime(2024, 2, 1, 12, 0, 0)),
            ('interpolated', '=', True),
        ], limit=1)
        old_price = feb_price.price

        last.price = 250.0
        (first + last).interpolate_cagr()
        feb_price.invalidate_recordset(['price'])
        self.assertNotEqual(old_price, feb_price.price)

    def test_asset_daily_price_computation_and_entrypoints(self):
        asset = self.env['investment.asset'].create({
            'ticker': 'DAILY-ASSET',
            'category_id': self.category.id,
            'currency_id': self.currency_eur.id,
        })
        now = fields.Datetime.now().replace(minute=0, second=0, microsecond=0)
        self.env['investment.asset.price'].create({
            'asset_id': asset.id,
            'time': now - timedelta(days=1200),
            'price': 10.0,
        })
        self.env['investment.asset.price'].create({
            'asset_id': asset.id,
            'time': now - timedelta(days=1, hours=10),
            'price': 11.0,
        })
        self.env['investment.asset.price'].create({
            'asset_id': asset.id,
            'time': now - timedelta(days=1, hours=1),
            'price': 12.0,
        })

        asset._compute_daily_prices()
        self.assertTrue(asset.last_price_id)
        self.assertTrue(asset.daily_price_id)
        self.assertTrue(asset.ytd_price_id)

        asset.action_compute_daily_prices()
        asset.cron_daily_prices()

    def test_asset_invalidate_prediction_ath_splits_and_daily_fallback(self):
        asset = self.env['investment.asset'].create({
            'ticker': 'ATH-SPLIT-ASSET',
            'category_id': self.category.id,
            'currency_id': self.currency_eur.id,
            'expected_yearly_appreciation': 0.05,
            'plausible_ath_drawdown': 0.25,
        })
        now = fields.Datetime.now().replace(minute=0, second=0, microsecond=0)
        predicted = self.env['investment.asset.price'].create({
            'asset_id': asset.id,
            'time': now + timedelta(days=5),
            'price': 200.0,
            'prediction': True,
        })
        asset.invalidate_predicted_prices()
        self.assertFalse(predicted.exists())

        price_1 = self.env['investment.asset.price'].create({
            'asset_id': asset.id,
            'time': now - timedelta(days=700),
            'price': 90.0,
        })
        price_2 = self.env['investment.asset.price'].create({
            'asset_id': asset.id,
            'time': now - timedelta(days=650),
            'price': 110.0,
        })
        price_3 = self.env['investment.asset.price'].create({
            'asset_id': asset.id,
            'time': now - timedelta(days=600),
            'price': 80.0,
        })
        self.env['investment.asset.price'].create({
            'asset_id': asset.id,
            'time': now - timedelta(days=550),
            'price': 120.0,
        })
        self.env['investment.asset.split'].create({
            'price_id': price_2.id,
            'factor': 2.0,
        })
        self.env['investment.asset.split'].create({
            'price_id': price_3.id,
            'factor': 1.5,
        })
        asset.last_price_id = asset.price_ids[:1]
        asset._compute_ath_price()
        self.assertGreater(asset.ath_price, 0.0)

        fallback_asset = self.env['investment.asset'].create({
            'ticker': 'YTD-FALLBACK-ASSET',
            'category_id': self.category.id,
            'currency_id': self.currency_eur.id,
        })
        old_price = self.env['investment.asset.price'].create({
            'asset_id': fallback_asset.id,
            'time': now - timedelta(days=900),
            'price': 77.0,
        })
        fallback_asset._compute_daily_prices()
        self.assertEqual(fallback_asset.ytd_price_id, old_price)

    def test_asset_inverse_last_price_new_day_and_position_inverse(self):
        asset = self.env['investment.asset'].create({
            'ticker': 'INV-PRICE',
            'category_id': self.category.id,
            'currency_id': self.currency_eur.id,
        })
        old = self.env['investment.asset.price'].create({
            'asset_id': asset.id,
            'time': fields.Datetime.now() - timedelta(days=2),
            'price': 10.0,
        })
        asset.last_price_id = old

        asset.last_price = 12.0
        self.assertNotEqual(asset.last_price_id, old)

        pos = self.env['investment.position'].create({
            'name': 'Position Inverse Last Price',
            'asset_id': asset.id,
            'portfolio_id': self.portfolio.id,
            'company_id': self.company.id,
        })
        pos.last_price = 13.0
        self.assertEqual(asset.last_price, 13.0)

    def test_asset_price_upsert_future_date_and_currency_rate_update(self):
        usd = self.env.ref('base.USD')
        usd.asset_id = self.asset

        future_time = fields.Datetime.now() + timedelta(days=5)
        self.asset.price_upsert(future_time, 123.0)
        self.assertLessEqual(self.asset.last_price_id.time, fields.Datetime.now())

        upsert_time = fields.Datetime.now() - timedelta(days=1)
        self.asset.price_upsert(upsert_time, 111.0)
        rate = self.env['res.currency.rate'].search([
            ('currency_id', '=', usd.id),
            ('name', '=', upsert_time.date()),
        ], limit=1)
        self.assertTrue(rate)

        self.asset.price_upsert(upsert_time, 222.0)
        self.assertEqual(rate.inverse_company_rate, 222.0)

    def test_asset_run_integration_paths_and_thread_entrypoint(self):
        endpoint_multi = self._create_test_endpoint(name='Endpoint Multi', multi_record=True)
        endpoint_single = self._create_test_endpoint(name='Endpoint Single', multi_record=False)

        closed_exchange = self.env['investment.exchange'].create({
            'name': 'Closed Exchange',
            'opening_time': 0.0,
            'closing_time': 0.0,
            'tz': 'UTC',
            'weekend_trading': True,
        })

        asset_multi_a = self.env['investment.asset'].create({
            'ticker': 'EPM-A',
            'category_id': self.category.id,
            'currency_id': self.currency_eur.id,
            'endpoint_id': endpoint_multi.id,
        })
        asset_multi_b = self.env['investment.asset'].create({
            'ticker': 'EPM-B',
            'category_id': self.category.id,
            'currency_id': self.currency_eur.id,
            'endpoint_id': endpoint_multi.id,
        })
        asset_single = self.env['investment.asset'].create({
            'ticker': 'EPS-A',
            'category_id': self.category.id,
            'currency_id': self.currency_eur.id,
            'endpoint_id': endpoint_single.id,
            'exchange_id': closed_exchange.id,
        })

        message_model = self.env['api.message']
        before = message_model.search_count([('endpoint_id', 'in', (endpoint_multi + endpoint_single).ids)])
        (asset_multi_a + asset_multi_b + asset_single).run_integration()
        after = message_model.search_count([('endpoint_id', 'in', (endpoint_multi + endpoint_single).ids)])
        self.assertGreater(after, before)

        force_before = message_model.search_count([('endpoint_id', '=', endpoint_single.id)])
        asset_single.with_context(force_fetch=True).run_integration()
        force_after = message_model.search_count([('endpoint_id', '=', endpoint_single.id)])
        self.assertGreater(force_after, force_before)

        asset_multi_a.thread_run_integration(asset_multi_a.id)
        self.assertTrue(message_model.search([('endpoint_id', '=', endpoint_multi.id)], limit=1))

    def test_asset_exec_integration_missing_recordset(self):
        self.env['investment.asset'].browse([99999999])._exec_integration()

    def test_milestone_states_copy_and_real_position(self):
        tomorrow = fields.Date.today() + timedelta(days=1)
        yesterday = fields.Date.today() - timedelta(days=1)

        ahead = self.env['investment.milestone'].create({
            'name': 'Ahead',
            'date': tomorrow,
            'domain': "[('id', '=', 0)]",
            'position': -1.0,
        })
        behind = self.env['investment.milestone'].create({
            'name': 'Behind',
            'date': tomorrow,
            'domain': "[('id', '=', 0)]",
            'position': 1.0,
        })
        reached = self.env['investment.milestone'].create({
            'name': 'Reached',
            'date': yesterday,
            'domain': "[('id', '=', 0)]",
            'position': -1.0,
        })
        missed = self.env['investment.milestone'].create({
            'name': 'Missed',
            'date': yesterday,
            'domain': "[('id', '=', 0)]",
            'position': 1.0,
        })

        self.assertEqual(ahead.state, 'ahead')
        self.assertEqual(behind.state, 'behind')
        self.assertEqual(reached.state, 'reached')
        self.assertEqual(missed.state, 'missed')
        self.assertIsInstance(ahead.real_position, float)

        copied = behind.copy()
        self.assertTrue(copied.name.endswith('(copy)'))

        count_before = self.env['investment.milestone'].search_count([])
        behind.copy_button()
        count_after = self.env['investment.milestone'].search_count([])
        self.assertEqual(count_after, count_before + 1)

        scratch = self.env['investment.milestone'].new({
            'name': 'No Date',
            'domain': "[]",
            'position': 100.0,
            'date': False,
        })
        scratch._compute_real_position()
        self.assertEqual(scratch.real_position, 100.0)

    def test_period_views_copy_dashboard_and_lock_shortcut(self):
        self.position.generate_timeseries()
        today = fields.Date.today()
        period = self.env['investment.period'].create({
            'name': 'Period Functional',
            'start_date': today - timedelta(days=45),
            'end_date': today,
            'domain': "[('id', '=', %d)]" % self.position.id,
            'company_id': self.company.id,
        })
        period.action_compute()

        self.assertEqual(period.action_view_timeseries()['res_model'], 'investment.timeseries')
        self.assertEqual(period.action_view_transactions()['res_model'], 'investment.position.transaction')
        self.assertEqual(period.action_view_positions()['res_model'], 'investment.period.position')

        copied = period.copy()
        self.assertIn('(copy)', copied.name)

        dashboard = self.env['investment.period'].get_dashboard(
            domain=[('id', '=', period.id)],
            specification={'name': {}, 'profit': {}},
        )
        self.assertIn('records', dashboard)

        self.env['investment.period'].browse([99999999]).action_compute()

    def test_period_xirr_exception_path(self):
        pos = self.env['investment.position'].create({
            'name': 'Yield Only XIRR',
            'asset_id': self.asset.id,
            'portfolio_id': self.portfolio.id,
            'company_id': self.company.id,
        })
        tx_time = fields.Datetime.now() - timedelta(days=3)
        self.env['investment.position.transaction'].create({
            'position_id': pos.id,
            'quantity': 0.0,
            'exchange_rate': 0.0,
            'payment': 25.0,
            'time': tx_time,
        })
        pos.generate_timeseries()

        period = self.env['investment.period'].create({
            'name': 'XIRR Exception',
            'start_date': tx_time.date() - timedelta(days=1),
            'end_date': tx_time.date(),
            'domain': "[('id', '=', %d)]" % pos.id,
            'company_id': self.company.id,
        })
        with mute_logger('odoo.addons.investment_portfolio.models.investment_period'):
            period.action_compute()
        self.assertIsInstance(period.annualized_irr, float)

    def test_position_note_action_documents(self):
        note = self.env['investment.position.note'].create({
            'name': 'Functional Note',
            'content': '<p>n</p>',
            'company_id': self.company.id,
        })

        action = note.with_context(
            action='investment_portfolio.action_position_notes',
            domain_ids=[note.id],
            custom_key='custom_value',
        ).action_documents()

        self.assertEqual(action['domain'], [('id', 'in', [note.id])])
        self.assertEqual(action['context'].get('custom_key'), 'custom_value')

    def test_position_move_search_helpers_and_string_time(self):
        move = self.env['investment.position.move'].create({
            'time': fields.Datetime.to_string(fields.Datetime.now()),
            'company_id': self.company.id,
        })
        self.tx_buy1.move_id = move

        move.invalidate_recordset(['portfolio_ids'])
        self.assertIn(self.portfolio, move.portfolio_ids)

        self.assertEqual(move._search_portfolio_ids('=', True), [('transaction_ids', '=', True)])
        self.assertEqual(move._search_position_ids('=', True), [('transaction_ids', '=', True)])

        negative_portfolio = move._search_portfolio_ids('not in', [self.portfolio.id])
        negative_position = move._search_position_ids('!=', self.position.id)
        self.assertEqual(negative_portfolio[0], '!')
        self.assertEqual(negative_position[0], '!')

    def test_transaction_misc_functional_paths(self):
        tx_new = self.env['investment.position.transaction'].new({
            'position_id': self.position.id,
            'quantity': 2.0,
            'exchange_rate': 50.0,
            'time': fields.Datetime.now(),
        })
        tx_new._onchange_quantity()
        self.assertEqual(tx_new.payment_currency, 100.0)

        self.tx_buy1._compute_kanban_quantity()
        self.assertTrue(self.tx_buy1.kanban_quantity)

        open_action = self.tx_buy1.open_form()
        self.assertEqual(open_action['res_id'], self.tx_buy1.id)

        asset = self.env['investment.asset'].create({
            'ticker': 'FILL-DAILY',
            'category_id': self.category.id,
            'currency_id': self.currency_eur.id,
        })
        pos = self.env['investment.position'].create({
            'name': 'Fill Daily Position',
            'asset_id': asset.id,
            'portfolio_id': self.portfolio.id,
            'company_id': self.company.id,
        })
        tx = self.env['investment.position.transaction'].create({
            'position_id': pos.id,
            'quantity': 1.0,
            'exchange_rate': 77.0,
            'payment': 77.0,
            'time': fields.Datetime.now() - timedelta(days=1),
        })
        tx._fill_daily_price()
        self.assertTrue(self.env['investment.asset.price'].search([('transaction_id', '=', tx.id)], limit=1))

        with self.assertRaises(ValidationError):
            self.env['investment.position.transaction'].browse().find_move()
        with self.assertRaises(ValidationError):
            self.env['investment.position.transaction'].browse().make_move()

    def test_transaction_find_move_and_currency_format_branches(self):
        move = self.env['investment.position.move'].create({
            'time': self.tx_buy1.time,
            'company_id': self.company.id,
        })
        self.tx_buy1.move_id = move
        with self.assertRaises(ValidationError):
            self.tx_buy1.find_move()
        self.tx_buy1.move_id = False

        tx_day_a = self.env['investment.position.transaction'].create({
            'position_id': self.position.id,
            'quantity': 1.0,
            'exchange_rate': 10.0,
            'payment': 10.0,
            'time': fields.Datetime.now() - timedelta(days=2),
        })
        tx_day_b = self.env['investment.position.transaction'].create({
            'position_id': self.position.id,
            'quantity': 1.0,
            'exchange_rate': 11.0,
            'payment': 11.0,
            'time': fields.Datetime.now() - timedelta(days=1),
        })
        with self.assertRaises(ValidationError):
            (tx_day_a + tx_day_b).find_move()

        usd = self.env.ref('base.USD')
        usd.position = 'before'
        rate = self.env['res.currency.rate'].create({
            'name': fields.Date.today(),
            'currency_id': usd.id,
            'company_id': self.company.id,
            'inverse_company_rate': 0.5,
        })
        usd_asset = self.env['investment.asset'].create({
            'ticker': 'USD-ASSET',
            'category_id': self.category.id,
            'currency_id': usd.id,
        })
        usd_position = self.env['investment.position'].create({
            'name': 'USD Position',
            'asset_id': usd_asset.id,
            'portfolio_id': self.portfolio.id,
            'company_id': self.company.id,
        })
        usd_tx = self.env['investment.position.transaction'].create({
            'position_id': usd_position.id,
            'quantity': 1.0,
            'exchange_rate': 20.0,
            'payment': 10.0,
            'time': fields.Datetime.now(),
        })
        usd_tx._compute_kanban_quantity()
        self.assertIn(f'@ {usd.symbol} ', usd_tx.kanban_quantity)

        usd_tx.currency_rate_id = rate
        usd_tx.payment_currency = 200.0
        usd_tx._inverse_payment_currency()
        self.assertAlmostEqual(usd_tx.payment, 100.0, places=2)

    def test_transaction_company_validation_paths(self):
        company_2 = self.env['res.company'].create({'name': 'Company Two'})
        portfolio_2 = self.env['investment.portfolio'].create({'name': 'Portfolio Two'})
        asset_2 = self.env['investment.asset'].create({
            'ticker': 'COMP2-ASSET',
            'category_id': self.category.id,
            'currency_id': self.currency_eur.id,
        })
        pos_2 = self.env['investment.position'].create({
            'name': 'Company Two Position',
            'asset_id': asset_2.id,
            'portfolio_id': portfolio_2.id,
            'company_id': company_2.id,
        })
        tx_2 = self.env['investment.position.transaction'].create({
            'position_id': pos_2.id,
            'quantity': 1.0,
            'exchange_rate': 10.0,
            'payment': 10.0,
            'time': fields.Datetime.now(),
        })

        with self.assertRaises(ValidationError):
            tx_2.make_move()
        with self.assertRaises(ValidationError):
            tx_2.find_move()

    def test_position_misc_functional_paths(self):
        endpoint = self._create_test_endpoint(name='Position Endpoint', multi_record=False)
        asset = self.env['investment.asset'].create({
            'ticker': 'POS-RUN',
            'category_id': self.category.id,
            'currency_id': self.currency_eur.id,
            'endpoint_id': endpoint.id,
        })
        self.env['investment.asset.price'].create({
            'asset_id': asset.id,
            'time': fields.Datetime.now() - timedelta(days=2),
            'price': 100.0,
        })
        asset.last_price_id = asset.price_ids[:1]
        pos = self.env['investment.position'].create({
            'name': 'Position Run',
            'asset_id': asset.id,
            'portfolio_id': self.portfolio.id,
            'company_id': self.company.id,
        })
        self.env['investment.position.transaction'].create({
            'position_id': pos.id,
            'quantity': 1.0,
            'exchange_rate': 100.0,
            'payment': 100.0,
            'time': fields.Datetime.now() - timedelta(days=2),
        })

        pos.generate_timeseries()
        pos.recompute_value()
        pos.run_integration()

        pos.web_refresh_prices([('id', '=', pos.id)])
        pos.action_show_price_change('daily_price_id')
        pos.action_show_profit_change('daily_timeseries_id')

        grouped = self.env['investment.position'].read_group(
            domain=[('id', 'in', (self.position + pos).ids)],
            fields=['profit:sum', 'investment:sum', 'profit_percent'],
            groupby=['portfolio_id'],
            lazy=False,
        )
        self.assertTrue(grouped)
        self.assertIn('profit_percent', grouped[0])

        pos._compute_chart_one_month()
        self.assertIn('data', pos.chart_one_month)

        dashboard = self.env['investment.position'].get_dashboard(
            domain=[('id', '=', pos.id)],
            specification={'name': {}, 'profit': {}},
            run_integration=True,
        )
        self.assertIn('records', dashboard)

    def test_position_generate_timeseries_edge_paths(self):
        no_tx_asset = self.env['investment.asset'].create({
            'ticker': 'NO-TX-ASSET',
            'category_id': self.category.id,
            'currency_id': self.currency_eur.id,
        })
        self.env['investment.asset.price'].create({
            'asset_id': no_tx_asset.id,
            'time': fields.Datetime.now() - timedelta(days=2),
            'price': 10.0,
        })
        no_tx_position = self.env['investment.position'].create({
            'name': 'No Transactions',
            'asset_id': no_tx_asset.id,
            'portfolio_id': self.portfolio.id,
            'company_id': self.company.id,
        })
        no_tx_position.generate_timeseries()

        no_price_asset = self.env['investment.asset'].create({
            'ticker': 'NO-PRICE-ASSET',
            'category_id': self.category.id,
            'currency_id': self.currency_eur.id,
        })
        no_price_position = self.env['investment.position'].create({
            'name': 'No Prices',
            'asset_id': no_price_asset.id,
            'portfolio_id': self.portfolio.id,
            'company_id': self.company.id,
        })
        self.env['investment.position.transaction'].create({
            'position_id': no_price_position.id,
            'quantity': 1.0,
            'exchange_rate': 10.0,
            'payment': 10.0,
            'time': fields.Datetime.now() - timedelta(days=2),
        })
        no_price_position.generate_timeseries()

        delayed_price_asset = self.env['investment.asset'].create({
            'ticker': 'DELAYED-PRICE-ASSET',
            'category_id': self.category.id,
            'currency_id': self.currency_eur.id,
        })
        delayed_price_position = self.env['investment.position'].create({
            'name': 'Delayed Price Position',
            'asset_id': delayed_price_asset.id,
            'portfolio_id': self.portfolio.id,
            'company_id': self.company.id,
        })
        self.env['investment.position.transaction'].create({
            'position_id': delayed_price_position.id,
            'quantity': 1.0,
            'exchange_rate': 9.0,
            'payment': 9.0,
            'time': fields.Datetime.now() - timedelta(days=5),
        })
        self.env['investment.asset.price'].create({
            'asset_id': delayed_price_asset.id,
            'time': fields.Datetime.now() - timedelta(days=2),
            'price': 10.0,
        })
        delayed_price_asset.last_price_id = delayed_price_asset.price_ids[:1]
        delayed_price_position.generate_timeseries()

        future_asset = self.env['investment.asset'].create({
            'ticker': 'FUTURE-TX-ASSET',
            'category_id': self.category.id,
            'currency_id': self.currency_eur.id,
        })
        self.env['investment.asset.price'].create({
            'asset_id': future_asset.id,
            'time': fields.Datetime.now(),
            'price': 10.0,
        })
        future_asset.last_price_id = future_asset.price_ids[:1]
        future_position = self.env['investment.position'].create({
            'name': 'Future Start Position',
            'asset_id': future_asset.id,
            'portfolio_id': self.portfolio.id,
            'company_id': self.company.id,
        })
        self.env['investment.position.transaction'].create({
            'position_id': future_position.id,
            'quantity': 1.0,
            'exchange_rate': 10.0,
            'payment': 10.0,
            'time': fields.Datetime.now() + timedelta(days=1),
        })
        future_position.generate_timeseries()
        self.assertTrue(self.env['investment.timeseries'].search([
            ('position_id', '=', future_position.id),
            ('date', '=', fields.Date.today()),
        ], limit=1))

    def test_position_generate_timeseries_existing_prediction_today_and_forced_today(self):
        now = fields.Datetime.now().replace(minute=0, second=0, microsecond=0)
        asset = self.env['investment.asset'].create({
            'ticker': 'TS-EXISTING-ASSET',
            'category_id': self.category.id,
            'currency_id': self.currency_eur.id,
        })
        self.env['investment.asset.price'].create({
            'asset_id': asset.id,
            'time': now - timedelta(days=10),
            'price': 100.0,
        })
        latest_price = self.env['investment.asset.price'].create({
            'asset_id': asset.id,
            'time': now - timedelta(hours=1),
            'price': 105.0,
        })
        asset.last_price_id = latest_price
        position = self.env['investment.position'].create({
            'name': 'Timeseries Existing Position',
            'asset_id': asset.id,
            'portfolio_id': self.portfolio.id,
            'company_id': self.company.id,
            'plan_months': 0,
        })
        self.env['investment.position.transaction'].create({
            'position_id': position.id,
            'quantity': 1.0,
            'exchange_rate': 100.0,
            'payment': 100.0,
            'time': now - timedelta(days=9),
        })
        self.env['investment.timeseries'].create({
            'position_id': position.id,
            'date': fields.Date.today(),
            'price_id': latest_price.id,
        })
        prediction_date = fields.Date.today().replace(month=12, day=31)
        if prediction_date <= fields.Date.today():
            prediction_date = prediction_date.replace(year=prediction_date.year + 1)
        self.env['investment.timeseries'].create({
            'position_id': position.id,
            'date': prediction_date,
            'price_id': latest_price.id,
        })
        position.generate_timeseries()

        future_asset = self.env['investment.asset'].create({
            'ticker': 'TS-FUTURE-ASSET',
            'category_id': self.category.id,
            'currency_id': self.currency_eur.id,
        })
        self.env['investment.asset.price'].create({
            'asset_id': future_asset.id,
            'time': now - timedelta(days=1),
            'price': 10.0,
        })
        future_asset.last_price_id = future_asset.price_ids[:1]
        future_position = self.env['investment.position'].create({
            'name': 'Timeseries Future Position',
            'asset_id': future_asset.id,
            'portfolio_id': self.portfolio.id,
            'company_id': self.company.id,
            'plan_months': 0,
        })
        future_tx = self.env['investment.position.transaction'].create({
            'position_id': future_position.id,
            'quantity': 0.0,
            'exchange_rate': 0.0,
            'payment': 10.0,
            'time': datetime(2056, 1, 5, 12, 0, 0),
        })
        self.assertEqual(future_tx.time.year, 2056)
        future_position.generate_timeseries()
        self.assertTrue(self.env['investment.timeseries'].search([
            ('position_id', '=', future_position.id),
            ('date', '=', fields.Date.today()),
        ], limit=1))

    def test_position_generate_plan_extra_paths(self):
        now = fields.Datetime.now()

        no_qty_pos = self.env['investment.position'].create({
            'name': 'No Qty Plan',
            'asset_id': self.asset.id,
            'portfolio_id': self.portfolio.id,
            'company_id': self.company.id,
            'plan_type': 'acquire',
            'plan_months': 3,
        })
        predicted = self.env['investment.position.transaction'].create({
            'position_id': no_qty_pos.id,
            'quantity': 1.0,
            'exchange_rate': 1.0,
            'payment': 1.0,
            'time': now + timedelta(days=10),
            'usage': 'prediction',
        })
        no_qty_pos.generate_plan()
        self.assertFalse(predicted.exists())

        auto_realize_pos = self.env['investment.position'].create({
            'name': 'Auto Realize Plan',
            'asset_id': self.asset.id,
            'portfolio_id': self.portfolio.id,
            'company_id': self.company.id,
            'plan_type': 'acquire',
            'plan_auto_realize': True,
            'plan_start_date': fields.Date.today() - timedelta(days=60),
            'plan_months': 1,
            'plan_payment': 10.0,
        })
        self.env['investment.position.transaction'].create({
            'position_id': auto_realize_pos.id,
            'quantity': 1.0,
            'exchange_rate': 10.0,
            'payment': 10.0,
            'time': now - timedelta(days=120),
        })
        old_prediction = self.env['investment.position.transaction'].create({
            'position_id': auto_realize_pos.id,
            'quantity': 0.1,
            'exchange_rate': 10.0,
            'payment': 1.0,
            'time': now - timedelta(days=10),
            'usage': 'prediction',
        })
        auto_realize_pos.generate_plan()
        self.assertFalse(old_prediction.prediction)

        skip_all_past_pos = self.env['investment.position'].create({
            'name': 'Skip Past Plan',
            'asset_id': self.asset.id,
            'portfolio_id': self.portfolio.id,
            'company_id': self.company.id,
            'plan_type': 'acquire',
            'plan_start_date': fields.Date.today() - timedelta(days=365),
            'plan_months': 1,
            'plan_allow_past': False,
            'plan_payment': 10.0,
        })
        skip_all_past_pos.generate_plan()
        self.assertFalse(skip_all_past_pos.plan_transaction_ids)

        cashflow_pos = self.env['investment.position'].create({
            'name': 'Cashflow Plan',
            'asset_id': self.asset.id,
            'portfolio_id': self.portfolio.id,
            'company_id': self.company.id,
            'plan_type': 'cashflow',
            'plan_start_date': fields.Date.today() + timedelta(days=1),
            'plan_months': 1,
            'plan_yield': 15.0,
            'plan_cost': 4.0,
            'plan_allow_past': True,
        })
        cashflow_pos.generate_plan()
        predicted = cashflow_pos.plan_transaction_ids
        self.assertTrue(predicted.filtered(lambda t: t.ttype == 'yield'))
        self.assertTrue(predicted.filtered(lambda t: t.ttype == 'cost'))

    def test_position_short_fifo_paths_and_misc_entrypoints(self):
        asset = self.env['investment.asset'].create({
            'ticker': 'SHORT-ASSET',
            'category_id': self.category.id,
            'currency_id': self.currency_eur.id,
        })
        self.env['investment.asset.price'].create({
            'asset_id': asset.id,
            'time': fields.Datetime.now() - timedelta(days=2),
            'price': 100.0,
        })
        pos = self.env['investment.position'].create({
            'name': 'Short Position',
            'asset_id': asset.id,
            'portfolio_id': self.portfolio.id,
            'company_id': self.company.id,
        })
        self.env['investment.position.transaction'].create({
            'position_id': pos.id,
            'quantity': -2.0,
            'exchange_rate': 100.0,
            'payment': 200.0,
            'time': fields.Datetime.now() - timedelta(days=1),
        })

        pos._compute_position_aggregate()
        self.assertLess(pos.quantity, 0.0)
        self.assertLess(pos.cost_basis, 0.0)

        self.env['investment.position'].new({
            'name': 'Unsaved',
            'asset_id': asset.id,
            'portfolio_id': self.portfolio.id,
            'company_id': self.company.id,
        }).update_realized_fifo()

        for any_asset in self.env['investment.asset'].search([]).filtered(lambda a: not a.last_price_id):
            if any_asset.price_ids:
                any_asset.last_price_id = any_asset.price_ids[:1]
            else: # pragma: no cover
                any_asset.last_price_id = self.env['investment.asset.price'].create({
                    'asset_id': any_asset.id,
                    'time': fields.Datetime.now(),
                    'price': 1.0,
                })

        self.env['investment.position'].cron_create_time_series()

    def test_exchange_additional_branches(self):
        ex = self.env['investment.exchange'].create({
            'name': 'Branch Exchange',
            'opening_time': 0.0,
            'closing_time': 0.0,
            'tz': 'UTC',
            'weekend_trading': True,
        })
        ex._compute_open_close()

        self.env['investment.exchange.gap'].create({
            'exchange_id': ex.id,
            'date': ex.next_open.date(),
            'name': 'Forced Gap',
            'closing_time': 0.0,
        })
        ex._compute_open_close()
        self.assertTrue(ex.next_open)
        self.assertTrue(ex.next_close)

        gap = self.env['investment.exchange.gap'].new({
            'exchange_id': ex.id,
            'name': 'No Date Gap',
            'date': False,
            'closing_time': 0.0,
        })
        gap._compute_closing_datetime()
        self.assertFalse(gap.closing_datetime)

    def test_timeseries_quarter_and_no_position_record(self):
        asset = self.env['investment.asset'].create({
            'ticker': 'TS-QUARTER',
            'category_id': self.category.id,
            'currency_id': self.currency_eur.id,
        })
        price = self.env['investment.asset.price'].create({
            'asset_id': asset.id,
            'time': datetime(2024, 3, 31, 12, 0, 0),
            'price': 10.0,
        })
        pos = self.env['investment.position'].create({
            'name': 'Quarter Position',
            'asset_id': asset.id,
            'portfolio_id': self.portfolio.id,
            'company_id': self.company.id,
        })
        ts = self.env['investment.timeseries'].create({
            'position_id': pos.id,
            'price_id': price.id,
            'date': date(2024, 3, 31),
        })
        self.assertEqual(ts.granularity, '2_quaterly')

        scratch = self.env['investment.timeseries'].new({
            'date': fields.Date.today(),
        })
        scratch._compute_timeseries_aggregate()

    def test_period_cost_branch_is_included_in_compute(self):
        asset = self.env['investment.asset'].create({
            'ticker': 'PERIOD-COST-ASSET',
            'category_id': self.category.id,
            'currency_id': self.currency_eur.id,
        })
        last_price = self.env['investment.asset.price'].create({
            'asset_id': asset.id,
            'time': fields.Datetime.now() - timedelta(days=4),
            'price': 10.0,
        })
        asset.last_price_id = last_price
        position = self.env['investment.position'].create({
            'name': 'Period Cost Position',
            'asset_id': asset.id,
            'portfolio_id': self.portfolio.id,
            'company_id': self.company.id,
            'plan_months': 0,
        })
        self.env['investment.position.transaction'].create({
            'position_id': position.id,
            'quantity': 2.0,
            'exchange_rate': 10.0,
            'payment': 20.0,
            'time': fields.Datetime.now() - timedelta(days=3),
        })
        cost_tx = self.env['investment.position.transaction'].create({
            'position_id': position.id,
            'quantity': 0.0,
            'exchange_rate': 0.0,
            'payment': -5.0,
            'time': fields.Datetime.now() - timedelta(days=2),
        })
        position.generate_timeseries()

        period = self.env['investment.period'].create({
            'name': 'Period Cost Branch',
            'start_date': fields.Date.today() - timedelta(days=5),
            'end_date': fields.Date.today() - timedelta(days=1),
            'domain': "[('id', '=', %d)]" % position.id,
            'company_id': self.company.id,
        })
        period.action_compute()
        self.assertIn(cost_tx, period.transaction_ids)
