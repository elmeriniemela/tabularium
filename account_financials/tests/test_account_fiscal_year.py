# -*- coding: utf-8 -*-

import base64
from datetime import date

from markupsafe import Markup

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged
from odoo.tools import misc

from odoo.addons.account_financials.models import account_fiscal_year


@tagged('post_install', '-at_install')
class TestAccountFiscalYear(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls._year_seq = 2090

    def _new_fiscal_year(self):
        year = type(self)._year_seq
        type(self)._year_seq += 1
        return self.env['account.fiscal.year'].create({
            'name': f'FY {year}',
            'date_from': date(year, 1, 1),
            'date_to': date(year, 12, 31),
            'company_id': self.company.id,
        })

    def test_tmp_odt_and_format_multiline_value(self):
        with account_fiscal_year.tmp_odt() as tmp_file:
            self.assertTrue(tmp_file.name.endswith('odt'))
            tmp_file.write(b'x')
            tmp_file.seek(0)
            self.assertEqual(tmp_file.read(), b'x')

        formatted = account_fiscal_year.format_multiline_value("row\n\t<&>")
        self.assertIsInstance(formatted, Markup)
        self.assertEqual(
            str(formatted),
            "row<text:line-break/><text:s/><text:s/><text:s/><text:s/>&lt;&amp;&gt;",
        )
        self.assertEqual(account_fiscal_year.format_multiline_value(""), "")
        self.assertEqual(account_fiscal_year.format_multiline_value(None), "")

    def test_copy_with_and_without_defaults(self):
        fiscal_year = self._new_fiscal_year()

        default_copy = fiscal_year.copy()
        self.assertEqual(default_copy.date_from, date(fiscal_year.date_from.year + 1, 1, 1))
        self.assertEqual(default_copy.date_to, date(fiscal_year.date_to.year + 1, 12, 31))
        self.assertEqual(default_copy.name, f'{fiscal_year.name} (copy)')

        explicit_copy = fiscal_year.copy({
            'name': 'Explicit Copy',
            'date_from': date(2200, 1, 1),
            'date_to': date(2200, 12, 31),
        })
        self.assertEqual(explicit_copy.name, 'Explicit Copy')
        self.assertEqual(explicit_copy.date_from, date(2200, 1, 1))
        self.assertEqual(explicit_copy.date_to, date(2200, 12, 31))

    def test_compute_format_dates_and_place(self):
        self.company.city = 'Helsinki'
        fiscal_year = self._new_fiscal_year()

        fiscal_year._compute_format_date()
        self.assertEqual(fiscal_year.format_date_from, misc.format_date(self.env, fiscal_year.date_from))
        self.assertEqual(
            fiscal_year.format_date_from_previous,
            misc.format_date(self.env, date(fiscal_year.date_from.year - 1, 1, 1)),
        )
        self.assertEqual(fiscal_year.format_date_to, misc.format_date(self.env, fiscal_year.date_to))
        self.assertEqual(
            fiscal_year.format_date_to_previous,
            misc.format_date(self.env, date(fiscal_year.date_to.year - 1, 12, 31)),
        )
        self.assertEqual(
            fiscal_year.format_date_expire,
            misc.format_date(self.env, date(fiscal_year.date_to.year + 10, 12, 31)),
        )

        fiscal_year._compute_place_and_date()
        self.assertEqual(
            fiscal_year.place_and_date,
            f'Helsinki, {misc.format_date(self.env, fields.Date.today())}',
        )

    def test_compute_logo_file_type(self):
        for magic, expected_file_type in account_fiscal_year.FILETYPE_BASE64_MAGICWORD.items():
            company = self.env['res.company'].new({'logo': magic + b'AAA'})
            fiscal_year = self.env['account.fiscal.year'].new({'company_id': company})
            fiscal_year._compute_logo_ftype()
            self.assertEqual(fiscal_year.logo_ftype, expected_file_type)

        company = self.env['res.company'].new({'logo': b'ZAAA'})
        fiscal_year = self.env['account.fiscal.year'].new({'company_id': company})
        fiscal_year._compute_logo_ftype()
        self.assertEqual(fiscal_year.logo_ftype, 'png')

        company = self.env['res.company'].new({'logo': False})
        fiscal_year = self.env['account.fiscal.year'].new({'company_id': company})
        fiscal_year._compute_logo_ftype()
        self.assertEqual(fiscal_year.logo_ftype, 'png')

    def test_check_dates_validation_errors(self):
        with self.assertRaises(ValidationError):
            self.env['account.fiscal.year'].create({
                'name': 'Invalid date range',
                'date_from': date(2300, 1, 2),
                'date_to': date(2300, 1, 1),
                'company_id': self.company.id,
            })

        child_company = self.env['res.company'].create({
            'name': 'Child company',
            'parent_id': self.company.id,
        })
        with self.assertRaises(ValidationError):
            self.env['account.fiscal.year'].create({
                'name': 'Child company fiscal year',
                'date_from': date(2301, 1, 1),
                'date_to': date(2301, 12, 31),
                'company_id': child_company.id,
            })

        self.env['account.fiscal.year'].create({
            'name': 'Existing fiscal year',
            'date_from': date(2302, 1, 1),
            'date_to': date(2302, 12, 31),
            'company_id': self.company.id,
        })
        with self.assertRaises(ValidationError):
            self.env['account.fiscal.year'].create({
                'name': 'Overlapping fiscal year',
                'date_from': date(2302, 6, 1),
                'date_to': date(2303, 5, 31),
                'company_id': self.company.id,
            })

    def test_display_address_and_report_line_wrappers(self):
        fiscal_year = self._new_fiscal_year()
        fiscal_year = fiscal_year.with_context(allowed_company_ids=[self.company.id])
        self.assertEqual(
            fiscal_year.py3o_display_address(),
            self.company.partner_id._display_address(without_company=True),
        )

        pl_lines = fiscal_year.py3o_pl_lines()
        if pl_lines:
            self.assertIn('name', pl_lines[0])
            self.assertIn('col_1', pl_lines[0])
            self.assertIn('col_2', pl_lines[0])
            self.assertIsInstance(pl_lines[0]['name'], Markup)


    def test_render_financials_creates_attachment(self):
        fiscal_year = self._new_fiscal_year()
        with misc.file_open('account_financials/tests/test.odt', 'rb') as template_file:
            template_datas = base64.b64encode(template_file.read())
        fiscal_year.financials_template_id = self.env['ir.attachment'].create({
            'name': 'financials-template.odt',
            'type': 'binary',
            'datas': template_datas,
        })

        attachment_domain = [
            ('res_model', '=', fiscal_year._name),
            ('res_id', '=', fiscal_year.id),
        ]
        before_count = self.env['ir.attachment'].search_count(attachment_domain)
        fiscal_year.render_financials()

        after_count = self.env['ir.attachment'].search_count(attachment_domain)
        self.assertEqual(after_count, before_count + 1)
        attachment = self.env['ir.attachment'].search(attachment_domain, order='id desc', limit=1)
        result = base64.b64decode(attachment.datas)
        self.assertIn(b'PK', result)
