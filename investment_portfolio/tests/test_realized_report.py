# -*- coding: utf-8 -*-

from datetime import datetime, timedelta
from odoo.tests import tagged
from odoo.tools.misc import formatLang
from .common import InvestmentTestCommon


@tagged('post_install', '-at_install')
class TestRealizedReport(InvestmentTestCommon):

    def test_report_totals_for_selected_records(self):
        position = self.env['investment.position'].create({
            'name': 'Report Totals',
            'asset_id': self.asset.id,
            'portfolio_id': self.portfolio.id,
            'company_id': self.company.id,
        })
        now = datetime.now()
        self.env['investment.position.transaction'].create({
            'position_id': position.id,
            'quantity': 5.0,
            'exchange_rate': 10.0,
            'payment': 50.0,
            'time': now - timedelta(days=30),
        })
        self.env['investment.position.transaction'].create({
            'position_id': position.id,
            'quantity': 5.0,
            'exchange_rate': 20.0,
            'payment': 100.0,
            'time': now - timedelta(days=20),
        })
        self.env['investment.position.transaction'].create({
            'position_id': position.id,
            'quantity': -10.0,
            'exchange_rate': 30.0,
            'payment': 300.0,
            'time': now - timedelta(days=10),
        })
        position._compute_position_aggregate()

        realized = position.realized_ids.filtered(lambda rec: not rec.simulated)
        self.assertEqual(len(realized), 2)

        totals = realized._get_report_totals()
        self.assertEqual(totals['profit'], formatLang(self.env, 150.0, digits=2))
        self.assertEqual(totals['sell_price'], formatLang(self.env, 300.0, digits=2))
        self.assertEqual(totals['buy_price'], formatLang(self.env, 150.0, digits=2))

    def test_report_action_binding(self):
        report_action = self.env.ref('investment_portfolio.action_report_asset_realized')
        self.assertEqual(report_action.model, 'investment.asset.realized')
        self.assertTrue(report_action.multi)

    def test_report_render_qweb_html(self):
        self.position._compute_position_aggregate()
        realized = self.position.realized_ids.filtered(lambda rec: not rec.simulated)
        self.assertTrue(realized)

        report_action = self.env.ref('investment_portfolio.action_report_asset_realized')
        html, report_type = report_action._render_qweb_html(report_action, realized.ids)

        self.assertEqual(report_type, 'html')
        self.assertTrue(html)
