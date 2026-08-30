# -*- coding: utf-8 -*-

import base64
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
            'producer': "obj = {'from': 'get', 'username': username}",
            'consumer': "response = {'from': obj['from'], 'username': obj['username']}",
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
            'producer': "obj = {'auth': True, 'username': username}",
            'consumer': "response = {'auth': obj['auth'], 'username': obj['username']}",
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
        cls.endpoint_get_bytes = cls.Endpoint.create({
            'name': 'HTTP GET Bytes',
            'role': 'passive',
            'direction': 'outbound',
            'comm_method': 'http',
            'http_method': 'get',
            'file_format': 'bytes',
            'response_format': 'bytes',
            'location': 'tests_get_bytes',
            'authorization': 'bytes-token',
            'auto_code': False,
            'producer': "obj = b'#!/bin/sh'",
            'consumer': 'response = obj',
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
        cls.endpoint_upload = cls.Endpoint.create({
            'name': 'HTTP Upload',
            'role': 'passive',
            'direction': 'inbound',
            'comm_method': 'http',
            'http_method': 'post',
            'file_format': 'bytes',
            'response_format': 'json',
            'location': 'tests_upload',
            'authorization': False,
            'user_id': cls.env.ref('base.user_admin').id,
            'auto_code': False,
            'producer': "obj = files[0]['data']",
            'consumer': "response = [{'name': file['name'], 'filename': file['filename'], 'content_type': file['content_type'], 'size': len(file['data'])} for file in files]",
        })

    def test_get_converters_includes_wildcard(self):
        converters = self.env['ir.http']._get_converters()
        self.assertIn('wildcard', converters)

    def _basic_auth_header(self, username, token):
        credentials = base64.b64encode(f'{username}:{token}'.encode()).decode()
        return {'Authorization': f'Basic {credentials}'}

    def test_get_json_basic_auth_with_query_variables(self):
        response = self.url_open(
            '/api-v1/tests_get_json?foo=bar',
            headers=self._basic_auth_header('first-user', 'query-token'),
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertIn('application/json', response.headers['Content-Type'])
        self.assertEqual(response.json(), {'from': 'get', 'username': 'first-user'})

    def test_get_bytes(self):
        response = self.url_open(
            '/api-v1/tests_get_bytes',
            headers=self._basic_auth_header('user', 'bytes-token'),
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertIn('application/octet-stream', response.headers['Content-Type'])
        self.assertEqual(response.content, b'#!/bin/sh')

    def test_basic_auth_accepts_any_username(self):
        response = self.url_open(
            '/api-v1/tests_get_other_auth',
            headers=self._basic_auth_header('another-user', 'header-token'),
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertEqual(response.json(), {'auth': True, 'username': 'another-user'})

    def test_basic_auth_rejects_invalid_tokens_and_schemes(self):
        with mute_logger('odoo.addons.api_endpoint.controllers.api_controller'):
            missing = self.url_open('/api-v1/tests_get_json')
            wrong = self.url_open(
                '/api-v1/tests_get_json',
                headers=self._basic_auth_header('user', 'wrong-token'),
            )
            query = self.url_open('/api-v1/tests_get_json?Authorization=query-token')
            bearer = self.url_open(
                '/api-v1/tests_get_json',
                headers={'Authorization': 'Bearer query-token'},
            )
            malformed = self.url_open(
                '/api-v1/tests_get_json',
                headers={'Authorization': 'Basic !!!'},
            )
        self.assertEqual(missing.status_code, HTTPStatus.FORBIDDEN)
        self.assertEqual(wrong.status_code, HTTPStatus.FORBIDDEN)
        self.assertEqual(query.status_code, HTTPStatus.FORBIDDEN)
        self.assertEqual(bearer.status_code, HTTPStatus.FORBIDDEN)
        self.assertEqual(malformed.status_code, HTTPStatus.FORBIDDEN)

    def test_get_json_without_auth_token(self):
        response = self.url_open('/api-v1/tests_get_no_auth')
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertEqual(response.json(), {'public': True})

    def test_reserved_request_variables_are_rejected(self):
        with mute_logger('odoo.addons.api_endpoint.controllers.api_controller'):
            response = self.url_open(
                '/api-v1/tests_get_json?obj=evil',
                headers=self._basic_auth_header('user', 'query-token'),
            )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.endpoint_get.state, 'error')

    def test_username_request_variable_is_reserved(self):
        with mute_logger('odoo.addons.api_endpoint.controllers.api_controller'):
            response = self.url_open(
                '/api-v1/tests_get_json?username=spoofed',
                headers=self._basic_auth_header('user', 'query-token'),
            )
        self.assertEqual(response.status_code, HTTPStatus.BAD_REQUEST)

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

    def test_multipart_files_are_normalized(self):
        response = self.url_open(
            '/api-v1/tests_upload',
            files=[
                ('document', ('one.bin', b'one', 'application/octet-stream')),
                ('document', ('two.txt', b'two!', 'text/plain')),
            ],
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertEqual(response.json(), [
            {'name': 'document', 'filename': 'one.bin', 'content_type': 'application/octet-stream', 'size': 3},
            {'name': 'document', 'filename': 'two.txt', 'content_type': 'text/plain', 'size': 4},
        ])

        msg = self.env['api.message'].search([('endpoint_id', '=', self.endpoint_upload.id)], limit=1)
        self.assertEqual(msg._get_msg_globals()['files'][1]['data'], b'two!')

    def test_upload_endpoint_requires_one_file(self):
        response = self.url_open('/api-v1/upload', files={'file': ('test.bin', b'contents')})
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertEqual(response.json(), 'OK')

        with mute_logger('odoo.addons.api_endpoint.controllers.api_controller'):
            missing = self.url_open('/api-v1/upload', data='body')
            multiple = self.url_open('/api-v1/upload', files=[
                ('file', ('one.bin', b'one')),
                ('file', ('two.bin', b'two')),
            ])
        self.assertEqual(missing.status_code, HTTPStatus.BAD_REQUEST)
        self.assertEqual(multiple.status_code, HTTPStatus.BAD_REQUEST)

    def test_files_parameter_is_reserved(self):
        with mute_logger('odoo.addons.api_endpoint.controllers.api_controller'):
            response = self.url_open('/api-v1/tests_upload?files=value', data='body')
        self.assertEqual(response.status_code, HTTPStatus.BAD_REQUEST)

    def test_redirect_response(self):
        response = self.url_open(
            '/api-v1/tests_get_redirect',
            headers=self._basic_auth_header('user', 'redirect-token'),
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
            response = self.url_open(
                '/api-v1/tests_get_error',
                headers=self._basic_auth_header('user', 'error-token'),
            )
        self.assertEqual(response.status_code, HTTPStatus.INTERNAL_SERVER_ERROR)
        self.assertNotIn('RuntimeError', response.text)
        self.assertNotIn('controller boom', response.text)
