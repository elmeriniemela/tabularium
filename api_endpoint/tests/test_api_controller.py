# -*- coding: utf-8 -*-

from http import HTTPStatus

from odoo.tests import HttpCase, tagged
from odoo.tools import mute_logger


@tagged('post_install', '-at_install')
class TestApiController(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Endpoint = cls.env['api.endpoint']

        cls.endpoint_get = cls.Endpoint.create({
            'name': 'HTTP GET JSON',
            'role': 'passive',
            'direction': 'outbound',
            'comm_method': 'http',
            'http_method': 'get',
            'file_format': 'json',
            'response_format': 'json',
            'location': 'tests_get_json',
            'authorization': 'query-token',
            'auto_code': False,
            'producer': "obj = {'from': 'get'}",
            'consumer': "response = {'from': obj['from']}",
        })
        cls.endpoint_get_other_auth = cls.Endpoint.create({
            'name': 'HTTP GET Other Auth',
            'role': 'passive',
            'direction': 'outbound',
            'comm_method': 'http',
            'http_method': 'get',
            'file_format': 'json',
            'response_format': 'json',
            'location': 'tests_get_other_auth',
            'authorization': 'header-token',
            'auto_code': False,
            'producer': "obj = {'auth': True}",
            'consumer': "response = {'auth': obj['auth']}",
        })
        cls.endpoint_get_no_auth = cls.Endpoint.create({
            'name': 'HTTP GET No Auth',
            'role': 'passive',
            'direction': 'outbound',
            'comm_method': 'http',
            'http_method': 'get',
            'file_format': 'json',
            'response_format': 'json',
            'location': 'tests_get_no_auth',
            'authorization': False,
            'user_id': cls.env.ref('base.user_admin').id,
            'auto_code': False,
            'producer': "obj = {'public': True}",
            'consumer': "response = {'public': obj['public']}",
        })
        cls.endpoint_post_xml = cls.Endpoint.create({
            'name': 'HTTP POST XML',
            'role': 'passive',
            'direction': 'inbound',
            'comm_method': 'http',
            'http_method': 'post',
            'file_format': 'json',
            'response_format': 'xml',
            'location': 'tests_post_xml',
            'authorization': False,
            'user_id': cls.env.ref('base.user_admin').id,
            'auto_code': False,
            'producer': "obj = {'size': len(data)}",
            'consumer': "response = lxml.etree.fromstring(f\"<ok>{obj['size']}</ok>\")",
        })
        cls.endpoint_redirect = cls.Endpoint.create({
            'name': 'HTTP Redirect',
            'role': 'passive',
            'direction': 'outbound',
            'comm_method': 'http',
            'http_method': 'get',
            'file_format': 'json',
            'response_format': 'redirect',
            'location': 'tests_get_redirect',
            'authorization': 'redirect-token',
            'auto_code': False,
            'producer': "obj = {'redirect': True}",
            'consumer': "response = {'location': '/web/login', 'code': 302}",
        })
        cls.endpoint_error = cls.Endpoint.create({
            'name': 'HTTP Error',
            'role': 'passive',
            'direction': 'outbound',
            'comm_method': 'http',
            'http_method': 'get',
            'file_format': 'json',
            'response_format': 'json',
            'location': 'tests_get_error',
            'authorization': 'error-token',
            'auto_code': False,
            'producer': "raise RuntimeError('controller boom')",
            'consumer': "response = {'ok': False}",
        })

    def test_get_converters_includes_wildcard(self):
        converters = self.env['ir.http']._get_converters()
        self.assertIn('wildcard', converters)

    def test_get_json_header_auth_with_query_variables(self):
        response = self.url_open('/api-v1/tests_get_json?Authorization=query-token&foo=bar')
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertIn('application/json', response.headers['Content-Type'])
        self.assertEqual(response.json(), {'from': 'get'})

    def test_get_json_query_auth(self):
        response = self.url_open('/api-v1/tests_get_other_auth?Authorization=header-token')
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertEqual(response.json(), {'auth': True})

    def test_get_json_without_auth_token(self):
        response = self.url_open('/api-v1/tests_get_no_auth')
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertEqual(response.json(), {'public': True})

    def test_reserved_request_variables_are_rejected(self):
        with mute_logger('odoo.addons.api_endpoint.controllers.api_controller'):
            response = self.url_open('/api-v1/tests_get_json?Authorization=query-token&obj=evil')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.endpoint_get.state, 'error')

    def test_request_body_size_limit(self):
        Param = self.env['ir.config_parameter'].sudo()
        old_limit = Param.get_param('api_endpoint.max_request_bytes', '1048576')
        Param.set_param('api_endpoint.max_request_bytes', '2')
        try:
            with mute_logger('odoo.addons.api_endpoint.controllers.api_controller'):
                response = self.url_open(
                    '/api-v1/tests_post_xml',
                    data='abc',
                    headers={'Content-Type': 'text/plain'},
                )
            self.assertEqual(response.status_code, HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            self.assertNotIn('abc', response.text)
        finally:
            Param.set_param('api_endpoint.max_request_bytes', old_limit)

    def test_post_xml_response(self):
        response = self.url_open(
            '/api-v1/tests_post_xml',
            data='abc',
            headers={'Content-Type': 'text/plain'},
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertIn('text/xml', response.headers['Content-Type'])
        self.assertIn('<ok>3</ok>', response.text)

    def test_redirect_response(self):
        response = self.url_open(
            '/api-v1/tests_get_redirect?Authorization=redirect-token',
            allow_redirects=False,
        )
        self.assertIn(response.status_code, (HTTPStatus.FOUND, HTTPStatus.SEE_OTHER))
        self.assertTrue(response.headers['Location'].endswith('/web/login'))

    def test_missing_endpoint_errors_json_and_xml(self):
        with mute_logger('odoo.addons.api_endpoint.controllers.api_controller'):
            response_json = self.url_open('/api-v1/tests_missing')
        self.assertEqual(response_json.status_code, HTTPStatus.NOT_FOUND)
        self.assertIn('application/json', response_json.headers['Content-Type'])
        self.assertNotIn('Endpoint not found', response_json.text)

        with mute_logger('odoo.addons.api_endpoint.controllers.api_controller'):
            response_xml = self.url_open('/api-v1/tests_missing', headers={'Content-Type': 'text/xml'})
        self.assertEqual(response_xml.status_code, HTTPStatus.NOT_FOUND)
        self.assertIn('text/xml', response_xml.headers['Content-Type'])
        self.assertIn('<error>', response_xml.text)

    def test_producer_exception_returns_generic_500(self):
        with mute_logger('odoo.addons.api_endpoint.controllers.api_controller'):
            response = self.url_open('/api-v1/tests_get_error?Authorization=error-token')
        self.assertEqual(response.status_code, HTTPStatus.INTERNAL_SERVER_ERROR)
        self.assertNotIn('RuntimeError', response.text)
        self.assertNotIn('controller boom', response.text)
