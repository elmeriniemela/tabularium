# -*- coding: utf-8 -*-

import json
from http import HTTPStatus

from lxml import etree

from odoo import http
from odoo.tests import HttpCase, tagged
from odoo.tools import mute_logger


@tagged('post_install', '-at_install')
class TestXMLExportController(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({'name': 'Controller Partner'})

    def _xml_post(self, payload):
        return self.url_open(
            '/web/export/xml',
            data={
                'data': json.dumps(payload),
                'csrf_token': http.Request.csrf_token(self),
            },
        )

    def test_formats_route_includes_xml_tag(self):
        self.authenticate('admin', 'admin')

        response = self.url_open(
            '/web/export/formats',
            data=json.dumps({'params': {}}),
            headers={'Content-Type': 'application/json'},
        )

        self.assertEqual(response.status_code, HTTPStatus.OK)
        formats = json.loads(response.content)['result']
        self.assertIn('xml', [item['tag'] for item in formats])

    def test_xml_route_exports_records_by_ids(self):
        self.authenticate('admin', 'admin')
        response = self._xml_post({
            'model': 'res.partner',
            'fields': [{'name': 'name'}, {'name': 'id'}],
            'ids': [self.partner.id],
            'domain': [],
            'import_compat': False,
        })

        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertIn('text/xml', response.headers['Content-Type'])
        self.assertIn('.xml', response.headers['Content-Disposition'])

        root = etree.fromstring(response.content)
        self.assertEqual(root.tag, 'odoo')
        self.assertEqual(root.find('record/field[@name="name"]').text, self.partner.name)

    def test_xml_route_exports_records_by_domain(self):
        self.authenticate('admin', 'admin')
        response = self._xml_post({
            'model': 'res.partner',
            'fields': [{'name': 'name'}],
            'ids': [],
            'domain': [('id', '=', self.partner.id)],
            'import_compat': False,
        })

        self.assertEqual(response.status_code, HTTPStatus.OK)
        root = etree.fromstring(response.content)
        self.assertEqual(root.find('record/field[@name="name"]').text, self.partner.name)

    def test_xml_route_rejects_grouped_export(self):
        self.authenticate('admin', 'admin')

        with mute_logger('odoo.addons.xml_export.controllers.export'):
            response = self._xml_post({
                'model': 'res.partner',
                'fields': [{'name': 'name'}],
                'ids': [],
                'domain': [],
                'groupby': ['name'],
                'import_compat': False,
            })

        self.assertEqual(response.status_code, HTTPStatus.INTERNAL_SERVER_ERROR)
        self.assertIn('Odoo Server Error', response.text)
        self.assertIn('Exporting grouped data to XML is not supported.', response.text)

    def test_xml_route_removes_id_for_non_ordinary_model(self):
        self.authenticate('admin', 'admin')
        self.env['res.device.log'].sudo().create({
            'session_identifier': f'test-session-{self.partner.id}',
            'platform': 'linux',
            'browser': 'firefox',
            'revoked': False,
        })

        response = self._xml_post({
            'model': 'res.device',
            'fields': [{'name': 'id'}, {'name': 'session_identifier'}],
            'ids': [],
            'domain': [('session_identifier', '=', f'test-session-{self.partner.id}')],
            'import_compat': False,
        })

        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertIn('session_identifier', response.text)
        self.assertNotIn('<field name="id"', response.text)
