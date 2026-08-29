# -*- coding: utf-8 -*-

import base64
import io
import threading
import zipfile
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from xmlrpc.server import Fault, SimpleXMLRPCServer

import pandas
from lxml import etree
from werkzeug.datastructures import FileStorage

from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged, TransactionCase

from odoo.addons.api_endpoint.models.api_endpoint import (
    GlobalsDict,
    json_decoder,
    json_encoder,
    safe_eval,
)


@tagged('post_install', '-at_install')
class TestApiEndpoint(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ApiEndpoint = cls.env['api.endpoint']
        cls.ApiMessage = cls.env['api.message']
        cls.usage_field = cls.env['ir.model.fields'].search([
            ('model', '=', 'api.message'),
            ('name', '=', 'endpoint_id'),
        ], limit=1)
        cls._seq = 0

    def _new_endpoint(self, **overrides):
        type(self)._seq += 1
        vals = {
            'name': f'Endpoint {type(self)._seq}',
            'direction': 'outbound',
            'role': 'active',
            'comm_method': 'http',
            'http_method': 'get',
            'file_format': 'json',
            'response_format': 'json',
            'location': f'tests/{self._testMethodName}/{type(self)._seq}',
            'auto_code': False,
            'auto_consume': False,
            'auto_commit': False,
            'producer': "obj = {'ok': True}",
            'consumer': "response = {'ok': obj['ok']}",
        }
        vals.update(overrides)
        return self.env['api.endpoint'].create(vals)

    def _start_server(self, server):
        thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.01}, daemon=True)
        thread.start()
        self.addCleanup(server.shutdown)
        self.addCleanup(server.server_close)
        self.addCleanup(thread.join, 1)
        return server.server_address[1]

    def test_json_helpers_globalsdict_and_import_xml(self):
        dt = datetime(2024, 1, 2, 3, 4, 5)
        d = date(2024, 1, 3)
        self.assertEqual(json_encoder(dt), repr(dt))
        self.assertEqual(json_encoder(d), repr(d))
        with self.assertRaises(TypeError):
            json_encoder(object())

        decoded = json_decoder({
            'one': 'datetime.datetime(2024, 1, 2, 3, 4, 5)',
            'two': 'datetime.date(2024, 1, 3)',
            'three': 3,
        })
        self.assertEqual(decoded['one'], datetime(2024, 1, 2, 3, 4, 5))
        self.assertEqual(decoded['two'], date(2024, 1, 3))
        self.assertEqual(decoded['three'], 3)

        root = etree.fromstring(b'<odoo/>')

        globals_dict = GlobalsDict({'foo': 1})
        globals_dict['bar'] = 2
        self.assertEqual(globals_dict['bar'], 2)
        with self.assertRaises(UserError):
            globals_dict['foo'] = 9
        with self.assertRaises(UserError):
            globals_dict['msg'] = 'x'
        with self.assertRaises(UserError):
            globals_dict.update({'foo': 9})
        globals_dict.force_set('foo', 9)
        self.assertEqual(globals_dict['foo'], 9)

        for expr in ["open('/etc/passwd').read()", "eval('1 + 1')", "exec('x = 1')"]:
            with self.subTest(expr=expr), self.assertRaises(ValueError):
                safe_eval(expr, GlobalsDict({}))

        eval_globals = GlobalsDict({'foo': 1})
        safe_eval('bar = foo + 1', eval_globals, mode='exec')
        self.assertEqual(eval_globals['bar'], 2)

    def test_create_sequence_and_url_generation(self):
        endpoint = self.ApiEndpoint.create({
            'name': 'API Test 01',
            'location': 'tests/sequence',
        })
        self.assertTrue(endpoint.sequence_id)
        self.assertEqual(endpoint.sequence_id.prefix, 'api_test_01_')

        manual_sequence = self.env['ir.sequence'].create({
            'name': 'Manual API Sequence',
            'prefix': 'MANUAL_',
            'company_id': False,
            'padding': 4,
        })
        endpoint_manual = self.ApiEndpoint.create({
            'name': 'Manual Sequence Endpoint',
            'sequence_id': manual_sequence.id,
            'location': 'tests/manual-sequence',
        })
        self.assertEqual(endpoint_manual.sequence_id, manual_sequence)

        endpoint_with_auth = self._new_endpoint(role='passive', authorization='token-1')
        self.assertIn('/api-v1/', endpoint_with_auth.url)
        self.assertIn('Authorization=', endpoint_with_auth.url)
        self.assertIn('token-1', endpoint_with_auth.url)

        endpoint_without_auth = self._new_endpoint(role='passive', authorization=False, user_id=self.env.ref('base.user_admin').id)
        self.assertIn('/api-v1/', endpoint_without_auth.url)
        self.assertNotIn('Authorization=', endpoint_without_auth.url)

        active_endpoint = self._new_endpoint(role='active')
        self.assertFalse(active_endpoint.url)

    def test_public_http_endpoint_rejects_superuser(self):
        user_admin = self.env.ref('base.user_admin')
        endpoint = self._new_endpoint(
            role='passive',
            user_id=user_admin.id,
            authorization=False,
        )
        self.assertEqual(endpoint.user_id, user_admin)

        with self.assertRaises(ValidationError):
            self._new_endpoint(role='passive', authorization=False)

        with self.assertRaises(ValidationError):
            endpoint.user_id = self.env.user

    def test_hardcoded_templates(self):
        inbound_json = self._new_endpoint(direction='inbound', auto_code=True, file_format='json')
        self.assertIn('json.loads(data)', inbound_json.hardcoded_producer)

        inbound_xml = self._new_endpoint(
            direction='inbound',
            auto_code=True,
            file_format='xml',
            xslt='<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform"/>',
        )
        self.assertIn('lxml.etree.fromstring(data)', inbound_xml.hardcoded_producer)
        self.assertIn('lxml.etree.XSLT', inbound_xml.hardcoded_consumer)

        inbound_csv = self._new_endpoint(direction='inbound', auto_code=True, file_format='csv')
        self.assertIn('pandas.read_csv', inbound_csv.hardcoded_producer)

        inbound_zip = self._new_endpoint(direction='inbound', auto_code=True, file_format='zip')
        self.assertIn('zipfile.ZipFile', inbound_zip.hardcoded_producer)

        outbound_xml = self._new_endpoint(direction='outbound', auto_code=True, file_format='xml')
        self.assertIn('records.xml_export', outbound_xml.hardcoded_producer)

        outbound_xmlrpc = self._new_endpoint(comm_method='xmlrpc', auto_code=True)
        self.assertIn('self.xmlrpc', outbound_xmlrpc.hardcoded_producer)

        manual = self._new_endpoint(auto_code=False)
        self.assertEqual(manual.hardcoded_producer, '')
        self.assertEqual(manual.hardcoded_consumer, '')

    def test_usage_actions_message_count_and_active_flag(self):
        endpoint = self._new_endpoint()
        self.assertFalse(endpoint._get_usage_records())
        endpoint.usage_field_id = self.usage_field
        msg = self.ApiMessage.create({
            'endpoint_id': endpoint.id,
            'content': base64.b64encode(b'{}'),
        })

        endpoint._compute_usage_count()
        self.assertEqual(endpoint.usage_count, 1)
        self.assertEqual(endpoint._get_usage_records(), msg)

        action = endpoint.action_view_usage()
        self.assertEqual(action['res_model'], 'api.message')
        self.assertEqual(action['domain'], [('id', 'in', msg.ids)])

        endpoint._compute_msg_count()
        self.assertEqual(endpoint.msg_count, 1)

        endpoint.state = 'archived'
        endpoint._compute_active()
        self.assertFalse(endpoint.active)
        endpoint.state = 'active'
        endpoint._compute_active()
        self.assertTrue(endpoint.active)

    def test_gc_messages_unlinks_expired_messages(self):
        endpoint = self._new_endpoint(ttl=1)
        msg_old = self.ApiMessage.create({
            'endpoint_id': endpoint.id,
            'content': base64.b64encode(b'{}'),
        })
        msg_new = self.ApiMessage.create({
            'endpoint_id': endpoint.id,
            'content': base64.b64encode(b'{}'),
        })

        self.cr.execute(
            f"UPDATE {msg_old._table} SET create_date = (now() AT TIME ZONE 'UTC') - interval '5 days' WHERE id = %s",
            [msg_old.id],
        )
        self.cr.execute(
            f"UPDATE {msg_new._table} SET create_date = (now() AT TIME ZONE 'UTC') WHERE id = %s",
            [msg_new.id],
        )
        self.ApiEndpoint._gc_messages()

        self.assertFalse(msg_old.exists())
        self.assertTrue(msg_new.exists())

    def test_mark_error_and_mark_active(self):
        endpoint = self._new_endpoint()
        endpoint.allow_backoff = True
        endpoint._mark_error()
        self.assertEqual(endpoint.state, 'error')
        self.assertEqual(endpoint.backoff, 1)
        self.assertEqual(endpoint.to_skip, 1)

        endpoint._mark_error()
        self.assertEqual(endpoint.backoff, 2)
        self.assertEqual(endpoint.to_skip, 2)

        endpoint._mark_active()
        self.assertEqual(endpoint.state, 'active')
        self.assertEqual(endpoint.backoff, 0)
        self.assertEqual(endpoint.to_skip, 0)

    def test_action_execute_paths(self):
        skipped = self._new_endpoint(to_skip=2)
        skipped.action_execute()
        self.assertEqual(skipped.to_skip, 1)

        endpoint_assert = self._new_endpoint(auto_commit=False)
        with self.assertRaises(AssertionError):
            endpoint_assert.with_context(force_commit=False, raise_exc=False).action_execute()

        endpoint_ok = self._new_endpoint(
            initiator="self.produce({'ticker': 'ACME'})",
            producer="obj = {'ticker': ticker}",
            consumer='',
            auto_consume=False,
            auto_commit=False,
        )
        endpoint_ok.action_execute()
        self.assertTrue(endpoint_ok.msg_ids)

    def test_action_execute_error_path_marks_error(self):
        endpoint = self._new_endpoint(
            initiator=False,
        )
        with self.assertRaises(UserError):
            endpoint.with_context(force_commit=True).action_execute()

    def test_action_test_and_serialize(self):
        endpoint = self._new_endpoint(test_example='x = 1')
        endpoint.action_test()

        partner = self.env['res.partner'].create({'name': 'Serialize Partner'})
        globals_dict = endpoint._get_globals()
        serialized = endpoint._serialize_dict(globals_dict, {'partner': partner})
        self.assertIn("self.env['res.partner'].browse", serialized)

        nested = endpoint._serialize_dict(globals_dict, {'items': [{'partner': partner}]})
        self.assertEqual(safe_eval(nested, globals_dict)['items'][0]['partner'], partner)

    def test_produce_validates_variables(self):
        endpoint = self._new_endpoint(auto_commit=False)
        with self.assertRaises(UserError):
            endpoint.produce([])
        with self.assertRaises(UserError):
            endpoint.produce({1: 'value'})
        with self.assertRaisesRegex(UserError, r"variables\['value'\]"):
            endpoint.produce({'value': FileStorage(stream=io.BytesIO(b'data'))})
        self.assertFalse(endpoint.msg_ids)

        globals_dict = endpoint._get_globals()
        with self.assertRaises(UserError):
            endpoint._serialize_dict(globals_dict, [])

    def test_uploaded_file_variables_round_trip(self):
        endpoint = self._new_endpoint(
            file_format='bytes',
            producer="obj = files[0]['data']",
            consumer="response = {'filename': files[0]['filename']}",
        )
        files = [{
            'name': 'document',
            'filename': 'test.bin',
            'content_type': 'application/octet-stream',
            'data': b'contents',
        }]

        endpoint.produce({'files': files})

        globals_dict = endpoint.msg_ids._get_msg_globals()
        self.assertEqual(globals_dict['files'], files)
        self.assertEqual(globals_dict['obj'], b'contents')

    def test_produce_consume_action_consume_and_msg_globals(self):
        endpoint = self._new_endpoint(
            producer="obj = {'name': partner.name}",
            consumer="response = {'name': obj['name']}",
            response_format='json',
            auto_consume=False,
            auto_commit=False,
        )
        partner = self.env['res.partner'].create({'name': 'Message Partner'})

        endpoint.produce({'partner': partner})
        msg = endpoint.msg_ids
        self.assertEqual(msg.state, 'produced')

        globals_dict = msg._get_msg_globals()
        self.assertEqual(globals_dict['partner'], partner)

        endpoint._consume(globals_dict)
        self.assertEqual(msg.state, 'consumed')
        self.assertTrue(msg.response)

        endpoint.produce({'partner': partner})
        msg_to_consume = self.ApiMessage.search([
            ('endpoint_id', '=', endpoint.id),
            ('state', '=', 'produced'),
        ], limit=1)
        self.assertEqual(msg_to_consume.state, 'produced')
        msg_to_consume.action_consume()
        self.assertEqual(msg_to_consume.state, 'consumed')

    def test_produce_and_consume_error_paths(self):
        endpoint_recover = self._new_endpoint(auto_commit=False)
        endpoint_recover.state = 'error'
        endpoint_recover.backoff = 4
        endpoint_recover.to_skip = 0
        endpoint_recover.produce({})
        self.assertEqual(endpoint_recover.state, 'active')
        self.assertEqual(endpoint_recover.backoff, 0)
        self.assertEqual(endpoint_recover.to_skip, 0)

        endpoint_skip = self._new_endpoint(to_skip=1)
        globals_dict = endpoint_skip.produce({})
        self.assertEqual(endpoint_skip.to_skip, 0)
        self.assertNotIn('obj', globals_dict)

        with self.assertRaises(AssertionError):
            endpoint_skip.with_context(force_commit=False, raise_exc=False)._consume(endpoint_skip._get_globals())

        endpoint_no_msg = self._new_endpoint(
            consumer="response = {'ok': obj['ok']}",
            response_format='json',
        )
        globals_dict = endpoint_no_msg._get_globals()
        globals_dict['obj'] = {'ok': True}
        endpoint_no_msg._consume(globals_dict)
        self.assertEqual(globals_dict['response'], {'ok': True})

        with self.assertRaises(RuntimeError):
            endpoint_no_msg.ensure_response({})

    def test_produce_rejects_protected_variable_names(self):
        for variable_name in ['self', 'msg']:
            with self.subTest(variable_name=variable_name):
                endpoint = self._new_endpoint(auto_commit=False)
                with self.assertRaises(UserError):
                    endpoint.produce({variable_name: 'evil'})
                self.assertFalse(endpoint.msg_ids)

    def test_produce_error_paths_invalid_state_and_missing_obj(self):
        endpoint_invalid_state = self._new_endpoint(
            state='archived',
            auto_commit=False,
        )
        with self.assertRaises(UserError):
            endpoint_invalid_state.produce({})

        endpoint_missing_obj = self._new_endpoint(
            producer='value = 1',
            auto_commit=False,
        )
        with self.assertRaises(RuntimeError):
            endpoint_missing_obj.produce({})

    def test_consume_error_path_marks_message_error(self):
        endpoint = self._new_endpoint(
            producer="obj = {'ok': True}",
            consumer="raise UserError('consume boom')",
            auto_consume=False,
            auto_commit=True,
        )
        endpoint.produce({})

        msg = endpoint.msg_ids
        globals_dict = msg._get_msg_globals()
        with self.assertRaises(UserError):
            endpoint._consume(globals_dict)


    def test_conversion_helpers_and_type_assertions(self):
        endpoint = self._new_endpoint()

        json_bytes = endpoint.obj_to_bytes({
            'd': date(2024, 1, 1),
            'dt': datetime(2024, 1, 1, 1, 2, 3),
        }, 'json')
        json_obj = endpoint.bytes_to_obj(json_bytes, 'json')
        self.assertEqual(json_obj['d'], date(2024, 1, 1))
        self.assertEqual(json_obj['dt'], datetime(2024, 1, 1, 1, 2, 3))

        node = etree.Element('root')
        node.text = 'ok'
        xml_bytes = endpoint.obj_to_bytes(node, 'xml')
        xml_obj = endpoint.bytes_to_obj(xml_bytes, 'xml')
        self.assertEqual(xml_obj.tag, 'root')

        df = pandas.DataFrame({'a': [1, 2]})
        csv_bytes = endpoint.obj_to_bytes(df, 'csv')
        csv_obj = endpoint.bytes_to_obj(csv_bytes, 'csv')
        self.assertEqual(list(csv_obj['a']), [1, 2])

        zip_fp = io.BytesIO()
        with zipfile.ZipFile(zip_fp, mode='w', compression=zipfile.ZIP_DEFLATED) as zip_builder:
            zip_builder.writestr('x.txt', 'x')
        zip_obj_write = zipfile.ZipFile(io.BytesIO(zip_fp.getvalue()))
        zip_bytes = endpoint.obj_to_bytes(zip_obj_write, 'zip')
        zip_obj_write.close()
        zip_obj_read = endpoint.bytes_to_obj(zip_bytes, 'zip')
        self.assertIn('x.txt', zip_obj_read.namelist())
        zip_obj_read.close()

        self.assertEqual(endpoint.obj_to_bytes(b'raw', 'bytes'), b'raw')
        self.assertEqual(endpoint.bytes_to_obj(b'raw', 'bytes'), b'raw')

        with self.assertRaises(AssertionError):
            endpoint.assert_obj_type(1, 'json')
        with self.assertRaises(AssertionError):
            endpoint.assert_obj_type('raw', 'bytes')
        with self.assertRaises(NotImplementedError):
            endpoint.assert_obj_type({}, 'invalid')
        with self.assertRaises(NotImplementedError):
            endpoint.obj_to_bytes({}, 'invalid')
        with self.assertRaises(NotImplementedError):
            endpoint.bytes_to_obj(b'{}', 'invalid')

    def test_message_create_and_preview(self):
        endpoint_json = self._new_endpoint(file_format='json', response_format='json')
        msg = self.ApiMessage.create({
            'endpoint_id': endpoint_json.id,
            'content': base64.b64encode(b'{"x": 1}'),
            'response': base64.b64encode(b'{"y": 2}'),
        })
        self.assertTrue(msg.name.endswith('.json'))
        msg._compute_content_preview()
        msg._compute_response_preview()
        self.assertEqual(msg.content_preview, '{"x": 1}')
        self.assertEqual(msg.response_preview, '{"y": 2}')

        msg_ctx_default = self.ApiMessage.with_context(default_endpoint_id=endpoint_json.id).create({
            'content': base64.b64encode(b'x'),
            'response': base64.b64encode(b'y'),
        })
        msg_ctx_default._compute_content_preview()
        msg_ctx_default._compute_response_preview()
        self.assertEqual(msg_ctx_default.content_preview, 'x')
        self.assertEqual(msg_ctx_default.response_preview, 'y')

        endpoint_zip = self._new_endpoint(file_format='zip', response_format='zip')
        msg_zip = self.ApiMessage.create({
            'endpoint_id': endpoint_zip.id,
            'content': base64.b64encode(b'zip'),
            'response': base64.b64encode(b'zip'),
        })
        msg_zip._compute_content_preview()
        msg_zip._compute_response_preview()
        self.assertFalse(msg_zip.content_preview)
        self.assertFalse(msg_zip.response_preview)

    def test_gc_next_from_queue_and_cron_run(self):
        endpoint_queue = self._new_endpoint()
        endpoint_queue.produce({})
        queue_msg = endpoint_queue.next_from_queue()
        self.assertTrue(queue_msg)
        self.cr.execute(
            f"UPDATE {queue_msg._table} SET state='consumed' WHERE id=%s",
            [queue_msg.id],
        )
        self.assertFalse(endpoint_queue.next_from_queue())

        with self.assertRaises(ValidationError):
            self.ApiEndpoint.cron_run()

    def test_cron_run_handles_message_error_and_success(self):
        cron = self.env['ir.cron'].create({
            'name': f'API Endpoint Cron {self._testMethodName}',
            'model_id': self.env['ir.model']._get_id('api.endpoint'),
            'state': 'code',
            'code': 'model.cron_run()',
            'interval_number': 1,
            'interval_type': 'minutes',
            'user_id': self.env.user.id,
        })
        endpoint = self._new_endpoint(
            cron_id=cron.id,
            auto_consume=False,
            auto_commit=False,
            initiator='x = 1',
            consumer="response = {'ok': obj['ok']}",
        )

        msg_broken = self.ApiMessage.create({
            'endpoint_id': endpoint.id,
            'content': base64.b64encode(b'not-json'),
            'variables': '{}',
            'context': '{}',
        })
        endpoint.produce({})
        msg_valid = self.ApiMessage.search(
            [('endpoint_id', '=', endpoint.id), ('state', '=', 'produced'), ('id', '!=', msg_broken.id)],
            limit=1,
        )
        self.assertTrue(msg_valid)

        progress = self.env['ir.cron.progress'].create({'cron_id': cron.id})
        self.ApiEndpoint.with_context(ir_cron_progress_id=progress.id).cron_run()

        self.assertEqual(msg_broken.state, 'error')
        self.assertEqual(msg_valid.state, 'consumed')

    def test_xmlrpc_success_fault_and_protocol_error(self):
        endpoint = self._new_endpoint()

        xmlrpc_ok = SimpleXMLRPCServer(('127.0.0.1', 0), allow_none=True, logRequests=False)
        xmlrpc_ok.register_function(lambda value: value + 1, 'bump')
        port_ok = self._start_server(xmlrpc_ok)
        result = endpoint.xmlrpc(f'http://127.0.0.1:{port_ok}', 'bump', [3], verify_ssl=False)
        self.assertEqual(result, 4)

        xmlrpc_fault = SimpleXMLRPCServer(('127.0.0.1', 0), allow_none=True, logRequests=False)

        def _explode():
            raise Fault(1, 'boom')

        xmlrpc_fault.register_function(_explode, 'explode')
        port_fault = self._start_server(xmlrpc_fault)
        with self.assertRaises(UserError):
            endpoint.xmlrpc(f'http://127.0.0.1:{port_fault}', 'explode', [])

        class ErrorHandler(BaseHTTPRequestHandler):
            def do_POST(self):
                self.send_response(500)
                self.end_headers()
                self.wfile.write(b'error')

            def log_message(self, _fmt, *_args):
                return

        http_error = HTTPServer(('127.0.0.1', 0), ErrorHandler)
        port_error = self._start_server(http_error)
        with self.assertRaises(UserError):
            endpoint.xmlrpc(f'http://127.0.0.1:{port_error}', 'explode', [])
