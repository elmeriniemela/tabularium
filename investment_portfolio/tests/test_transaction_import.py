# -*- coding: utf-8 -*-

from odoo import Command
from odoo.tests import tagged

from .common import InvestmentTestCommon


@tagged('post_install', '-at_install')
class TestTransactionImport(InvestmentTestCommon):

    def test_company_rule_limits_visible_imports(self):
        other_company = self.env['res.company'].create({
            'name': 'Other Import Company',
        })
        user = self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Import User',
            'login': 'import-user',
            'email': 'import-user@example.com',
            'company_id': self.company.id,
            'company_ids': [Command.set([self.company.id])],
            'group_ids': [Command.set([
                self.env.ref('investment_portfolio.group_investment_user').id,
            ])],
        })
        visible_import = self.env['investment.transaction.import'].create({
            'name': 'Visible Import',
            'company_id': self.company.id,
        })
        hidden_import = self.env['investment.transaction.import'].create({
            'name': 'Hidden Import',
            'company_id': other_company.id,
        })

        imports = self.env['investment.transaction.import'].with_user(user).search([])

        self.assertIn(visible_import, imports)
        self.assertNotIn(hidden_import, imports)
