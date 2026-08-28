# -*- coding: utf-8 -*-

import base64
import io
from datetime import date
from types import SimpleNamespace
from zipfile import ZipFile

from lxml import etree
from markupsafe import Markup

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged
from odoo.tools import misc

from odoo.addons.account_financials.models import account_fiscal_year, odt_template


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

    def test_format_multiline_value(self):
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
        with ZipFile(io.BytesIO(result)) as rendered_odt:
            content = rendered_odt.read('content.xml')
        self.assertIn(self.company.name.encode(), content)
        self.assertNotIn(b'text:user-field-get text:name="py3o.', content)

    def test_odt_renderer_renders_headers_and_deduplicates_images(self):
        content_xml = b'''<?xml version="1.0" encoding="UTF-8"?>
            <office:document-content
                xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
                xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"
                xmlns:draw="urn:oasis:names:tc:opendocument:xmlns:drawing:1.0"
                xmlns:svg="urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0"
                xmlns:xlink="http://www.w3.org/1999/xlink">
                <office:body><office:text>
                    <text:p><text:user-field-get text:name="py3o.objects.report_title">report_title</text:user-field-get></text:p>
                    <draw:frame draw:name="py3o.image(objects.signature, 'png', height='2cm', isb64=True, keep_ratio=True)" svg:width="8cm"><draw:text-box/></draw:frame>
                    <draw:frame draw:name="py3o.image(objects.signature, 'png', height='2cm', isb64=True, keep_ratio=True)" svg:width="8cm"><draw:text-box/></draw:frame>
                    <draw:frame draw:name="py3o.image(objects.missing_logo, 'png', height='2cm', isb64=True, keep_ratio=True)" svg:width="2cm"><draw:text-box/></draw:frame>
                </office:text></office:body>
            </office:document-content>'''
        styles_xml = b'''<?xml version="1.0" encoding="UTF-8"?>
            <office:document-styles
                xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
                xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0"
                xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">
                <office:master-styles><style:master-page style:name="Synthetic">
                    <style:header><text:p>
                        <text:user-field-get text:name="py3o.objects.company.name">company.name</text:user-field-get>
                    </text:p></style:header>
                    <style:footer><text:p>
                        <text:user-field-get text:name="py3o.objects.company.registration">company.registration</text:user-field-get>
                        <text:text-input text:description="py3o://function=&quot;format_address(objects.company.address)&quot;">Company Address</text:text-input>
                    </text:p></style:footer>
                </style:master-page></office:master-styles>
            </office:document-styles>'''
        manifest_xml = b'''<?xml version="1.0" encoding="UTF-8"?>
            <manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0">
                <manifest:file-entry manifest:full-path="/" manifest:media-type="application/vnd.oasis.opendocument.text"/>
                <manifest:file-entry manifest:full-path="content.xml" manifest:media-type="text/xml"/>
                <manifest:file-entry manifest:full-path="styles.xml" manifest:media-type="text/xml"/>
            </manifest:manifest>'''
        signature = (
            b'iVBORw0KGgoAAAANSUhEUgAAAAMAAAABAQAAAAAzmykZAAAAIGNIUk0AAHomAACAhAAA+'
            b'gAAAIDoAAB1MAAA6mAAADqYAAAXcJy6UTwAAAACYktHRAAB3YoTpAAAAAd0SU1FB+oI'
            b'HBADKFMKaesAAAAldEVYdGRhdGU6Y3JlYXRlADIwMjYtMDgtMjhUMTY6MDM6NDArMDA6'
            b'MDCCdKUtAAAAJXRFWHRkYXRlOm1vZGlmeQAyMDI2LTA4LTI4VDE2OjAzOjQwKzAwOjAw'
            b'8ykdkQAAACh0RVh0ZGF0ZTp0aW1lc3RhbXAAMjAyNi0wOC0yOFQxNjowMzo0MCswMDow'
            b'MKQ8PE4AAAAKSURBVAjXY2AAAAACAAHiIbwzAAAAAElFTkSuQmCC'
        )

        template = io.BytesIO()
        with ZipFile(template, 'w') as archive:
            archive.writestr('mimetype', 'application/vnd.oasis.opendocument.text')
            archive.writestr('content.xml', content_xml)
            archive.writestr('styles.xml', styles_xml)
            archive.writestr('META-INF/manifest.xml', manifest_xml)

        objects = SimpleNamespace(
            report_title='Synthetic annual report',
            company=SimpleNamespace(
                name='Example Industries Ltd',
                registration='TEST-12345',
                address='Example Street 1\nExample City',
            ),
            signature=signature,
            missing_logo=False,
        )
        rendered = odt_template.render_odt_template(
            template.getvalue(),
            {
                'objects': objects,
                'format_address': account_fiscal_year.format_multiline_value,
            },
        )

        with ZipFile(io.BytesIO(rendered)) as archive:
            content = etree.fromstring(archive.read('content.xml'))
            styles = archive.read('styles.xml')
            manifest = archive.read('META-INF/manifest.xml')
            pictures = [name for name in archive.namelist() if name.startswith('Pictures/')]

        self.assertIn(b'Synthetic annual report', etree.tostring(content))
        self.assertIn(b'Example Industries Ltd', styles)
        self.assertIn(b'TEST-12345', styles)
        self.assertIn(b'Example Street 1', styles)
        self.assertIn(b'Example City', styles)
        self.assertIn(b'text:line-break', styles)
        self.assertNotIn(b'text:user-field-get', styles)
        self.assertNotIn(b'text:text-input', styles)

        namespaces = {
            'draw': odt_template.DRAW_NS,
            'svg': odt_template.SVG_NS,
            'xlink': odt_template.XLINK_NS,
        }
        image_frames = content.xpath('.//draw:frame[draw:image/@xlink:href]', namespaces=namespaces)
        self.assertEqual(len(image_frames), 2)
        self.assertEqual(
            {frame.get(f'{{{namespaces["svg"]}}}width') for frame in image_frames},
            {'6.000cm'},
        )
        image_paths = {
            frame.xpath('./draw:image/@xlink:href', namespaces=namespaces)[0]
            for frame in image_frames
        }
        self.assertEqual(len(image_paths), 1)
        self.assertEqual(pictures, list(image_paths))
        self.assertEqual(manifest.count(next(iter(image_paths)).encode()), 1)

        empty_frames = content.xpath('.//draw:frame[not(@*)]', namespaces=namespaces)
        self.assertEqual(len(empty_frames), 1)
        self.assertTrue(empty_frames[0].xpath('./draw:image[not(@*)]', namespaces=namespaces))
