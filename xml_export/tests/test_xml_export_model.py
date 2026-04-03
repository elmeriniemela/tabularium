# -*- coding: utf-8 -*-

from datetime import date

from lxml import etree

from odoo.tests import TransactionCase, tagged
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT, DEFAULT_SERVER_DATETIME_FORMAT


@tagged('post_install', '-at_install')
class TestXMLExportModel(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Partner = cls.env['res.partner']
        cls.ModelData = cls.env['ir.model.data'].sudo()

    def test_ensure_xmlid_create_and_reuse(self):
        partner = self.Partner.create({'name': 'XMLID Partner'})
        self.ModelData.search([
            ('model', '=', partner._name),
            ('res_id', '=', partner.id),
        ]).unlink()

        xmlid_map = partner.ensure_xmlid(
            idformat=lambda record: f'partner_{record.id}',
            module='xml_export_test',
        )
        self.assertEqual(
            xmlid_map[partner],
            f'xml_export_test.partner_{partner.id}',
        )

        all_model_data = self.ModelData.search([
            ('model', '=', partner._name),
            ('res_id', '=', partner.id),
        ])
        self.assertEqual(len(all_model_data), 1)

        reused_map = partner.ensure_xmlid(
            idformat=lambda record: f'partner_{record.id}',
            module='xml_export_test',
        )
        self.assertEqual(reused_map[partner], xmlid_map[partner])
        self.assertEqual(len(self.ModelData.search([
            ('model', '=', partner._name),
            ('res_id', '=', partner.id),
        ])), 1)

    def test_xml_recursive_export_with_one2many_and_unsupported_nested_field(self):
        parent = self.Partner.create({'name': 'Parent'})
        child = self.Partner.create({'name': 'Child', 'parent_id': parent.id})

        root = parent.xml_export(['name', '.id', 'parent_id/name', 'child_ids/name'])

        self.assertEqual(root.tag, 'odoo')
        record = root.find('record')
        self.assertTrue(record is not None)
        self.assertEqual(record.get('model'), 'res.partner')

        field_names = {field.get('name') for field in record.findall('field')}
        self.assertIn('name', field_names)
        self.assertIn('id', field_names)
        self.assertIn('child_ids', field_names)

        child_field = next(field for field in record.findall('field') if field.get('name') == 'child_ids')
        nested_record = child_field.find('record')
        self.assertTrue(nested_record is not None)
        nested_name_field = next(field for field in nested_record.findall('field') if field.get('name') == 'name')
        self.assertEqual(nested_name_field.text, child.name)

    def test_xml_basic_field_export_types(self):
        parent = self.Partner.create({'name': 'Parent Ref'})
        partner_plain = self.Partner.create({'name': 'Plain Text', 'active': False})
        partner_xml = self.Partner.create({'name': '<node/>'})
        partner_html = self.Partner.create({'name': '<div>'})
        partner_with_parent = self.Partner.create({'name': 'Child Ref', 'parent_id': parent.id})
        partner_without_parent = self.Partner.create({'name': 'No Parent'})
        currency = self.env.ref('base.USD')
        rate = self.env['res.currency.rate'].create({
            'name': date(2099, 1, 1),
            'rate': 2.5,
            'currency_id': currency.id,
            'company_id': self.env.company.id,
        })

        text_field = etree.Element('field')
        partner_plain._xml_basic_field_export('name', text_field)
        self.assertEqual(text_field.text, 'Plain Text')

        xml_field = etree.Element('field')
        partner_xml._xml_basic_field_export('name', xml_field)
        self.assertEqual(xml_field.get('type'), 'xml')
        self.assertEqual(xml_field[0].tag, 'node')

        html_field = etree.Element('field')
        partner_html._xml_basic_field_export('name', html_field)
        self.assertEqual(html_field.get('type'), 'html')
        self.assertEqual(html_field[0].tag, 'html')

        int_field = etree.Element('field')
        partner_plain._xml_basic_field_export('id', int_field)
        self.assertEqual(int_field.get('eval'), repr(partner_plain.id))

        bool_field = etree.Element('field')
        partner_plain._xml_basic_field_export('active', bool_field)
        self.assertEqual(bool_field.get('eval'), repr(False))

        float_field = etree.Element('field')
        rate._xml_basic_field_export('rate', float_field)
        self.assertEqual(float_field.get('eval'), repr(rate.rate))

        datetime_field = etree.Element('field')
        partner_plain._xml_basic_field_export('create_date', datetime_field)
        self.assertEqual(
            datetime_field.text,
            partner_plain.create_date.strftime(DEFAULT_SERVER_DATETIME_FORMAT),
        )

        date_field = etree.Element('field')
        rate._xml_basic_field_export('name', date_field)
        self.assertEqual(date_field.text, rate.name.strftime(DEFAULT_SERVER_DATE_FORMAT))

        many2one_field = etree.Element('field')
        partner_with_parent._xml_basic_field_export('parent_id', many2one_field)
        self.assertTrue(many2one_field.get('ref'))

        empty_many2one_field = etree.Element('field')
        partner_without_parent._xml_basic_field_export('parent_id', empty_many2one_field)
        self.assertEqual(empty_many2one_field.get('eval'), repr(False))
