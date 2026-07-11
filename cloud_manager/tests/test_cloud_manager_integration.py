# -*- coding: utf-8 -*-

import json
from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged
from odoo.tests.common import mute_logger
from odoo.addons.api_endpoint.models.api_endpoint import safe_eval


CLOUD_ENDPOINT_PRODUCER = """
if method == 'create':
    obj = "[options]\\naddons_path=/opt/odoo,/opt/custom_a\\n"
elif method == 'rebuild':
    obj = True
elif method == 'remove':
    obj = True
elif method == 'stop':
    obj = True
elif method == 'start':
    obj = True
elif method == 'restart':
    obj = True
elif method == 'self_upgrade':
    obj = True
elif method == 'upgrade':
    obj = 'upgrade-log'
elif method == 'fshealth':
    obj = 'fshealth-ok'
elif method == 'backup':
    obj = {'backups': [{
        'fname': 'backup-latest.zip',
        'timestamp': datetime.datetime.now(),
        'trigger': 'manual',
        'source': 'default',
    }]}
elif method == 'reset':
    obj = True
elif method == 'config':
    obj = True
elif method == 'sync_urls':
    obj = True
elif method == 'restore':
    obj = 'restore-log'
elif method == 'oca_migrate':
    obj = 'migrate-log'
elif method == 'ssl_renew':
    obj = 'ssl-ok'
elif method == 'agent_restart':
    obj = True
elif method == 'module_diff':
    obj = '' if args[1].startswith('empty') else 'module diff'
elif method == 'agent_diff':
    obj = '' if args[0].startswith('empty') else 'agent diff'
elif method == 'module_pull':
    obj = 'module-pulled'
elif method == 'agent_pull':
    obj = 'agent-pulled'
elif method == 'status':
    obj = {
        'timestamp': '2026-07-11 11:00:00',
        'agent': {
            'commit': 'agent-commit',
            'commit_date': '2024-01-02T03:04:05+00:00',
        },
        'instances': [{
            'uid': 'status-uid',
            'docker': {
                'Ports': [{'PublicPort': 54000}, {'PublicPort': 54001}],
                'State': 'running',
                'inspect': {'State': {'StartedAt': '2024-01-02T03:04:05+00:00'}},
            },
            'backups': [{
                'fname': 'status-backup.zip',
                'timestamp': '2024-01-02 03:04:05',
                'trigger': 'auto',
                'source': 'default',
            }],
        }],
        'modules': [{
            'name': 'odoo',
            'commit': 'odoo-commit-1',
            'commit_date': '2024-01-02T03:04:05+00:00',
            'url': 'https://example.invalid/odoo',
            'branch': 'main',
        }, {
            'name': 'custom_a',
            'commit': 'custom-commit-1',
            'commit_date': '2024-01-02T03:04:05+00:00',
            'url': 'https://example.invalid/custom_a',
            'branch': 'main',
        }],
        'hardware': {
            'cpu': {
                'usage_percent': 18.4,
            },
            'memory': {
                'total_gb': 15.62,
                'available_gb': 8.5,
                'used_gb': 7.13,
                'usage_percent': 45.6,
            },
            'disks': [{
                'mount': '/',
                'total_gb': 98.3,
                'used_gb': 54.69,
                'free_gb': 43.62,
                'usage_percent': 55.6,
            }, {
                'mount': '/data',
                'total_gb': 196.61,
                'used_gb': 98.3,
                'free_gb': 98.3,
                'usage_percent': 50.0,
            }],
        },
    }
else:
    obj = {
        'method': method,
        'args': args,
        'commit_before': commit_before,
    }
"""


DNS_ENDPOINT_PRODUCER = """
if kwargs['method'] == 'GET' and kwargs['url'].endswith('/dns_records'):
    obj = {'result': [{
        'name': 'fetched.example.com',
        'id': 'fetched-id',
        'ttl': 120,
        'type': 'A',
        'content': '1.2.3.4',
        'proxied': False,
    }]}
elif kwargs['method'] == 'POST':
    if kwargs['json']['name'].startswith('fail-create'):
        obj = {'success': False}
    else:
        obj = {
            'success': True,
            'result': {
                'id': 'created-' + kwargs['json']['name'].replace('.', '-'),
            },
        }
elif kwargs['method'] == 'PUT':
    obj = {'success': kwargs['json']['content'] != 'fail-content'}
elif kwargs['method'] == 'DELETE':
    rec_id = kwargs['url'].split('/')[-1]
    obj = {'result': {'id': rec_id}}
else:
    obj = {'result': []}
"""


@tagged('post_install', '-at_install')
class TestCloudManagerIntegration(TransactionCase):
    _seq = 0

    def setUp(self):
        super().setUp()
        cloudflare = self.env.ref('cloud_manager.endpoint_cloudflare_dns', raise_if_not_found=False)
        if cloudflare:
            cloudflare.state = 'archived'

    def _next_name(self, prefix):
        type(self)._seq += 1
        return f'{prefix} {type(self)._seq}'

    def _server_usage_field(self):
        return self.env['ir.model.fields'].search([
            ('model', '=', 'cloud.server'),
            ('name', '=', 'endpoint_id'),
        ], limit=1)

    def _dns_usage_field(self):
        return self.env['ir.model.fields'].search([
            ('model', '=', 'dns.zone'),
            ('name', '=', 'ns_endpoint_id'),
        ], limit=1)

    def _new_endpoint(self, name_prefix, producer, usage_field=False, **overrides):
        vals = {
            'name': self._next_name(name_prefix),
            'direction': 'outbound',
            'role': 'active',
            'comm_method': 'http',
            'http_method': 'post',
            'file_format': 'json',
            'response_format': 'json',
            'location': f'tests/{self._testMethodName}/{self._seq}',
            'auto_code': False,
            'auto_consume': False,
            'auto_commit': False,
            'producer': producer,
        }
        if usage_field:
            vals['usage_field_id'] = usage_field.id
        vals.update(overrides)
        return self.env['api.endpoint'].create(vals)

    def _new_server(self, endpoint, branch='main', cname='srv.example.com', **overrides):
        vals = {
            'name': self._next_name('Server'),
            'endpoint_id': endpoint.id,
            'branch': branch,
            'cname': cname,
        }
        vals.update(overrides)
        return self.env['cloud.server'].create(vals)

    def _new_server_module(self, server, name, **overrides):
        module = self.env['cloud.module'].search([('name', '=', name)], limit=1)
        if not module:
            module = self.env['cloud.module'].create({'name': name})
        vals = {
            'server_id': server.id,
            'module_id': module.id,
            'url': f'https://example.invalid/{name}',
            'branch': server.branch,
            'commit': f'{name}-commit',
            'commit_date': fields.Datetime.now(),
        }
        vals.update(overrides)
        return self.env['cloud.server.module'].create(vals)

    def _new_zone(self, name='example.com'):
        return self.env['dns.zone'].create({
            'name': name,
            'identifier': self._next_name('zone-id'),
        })

    def _new_instance(self, server, name='Instance', **overrides):
        if not server.module_ids:
            self._new_server_module(server, 'odoo')
        vals = {
            'name': self._next_name(name),
            'server_id': server.id,
        }
        vals.update(overrides)
        return self.env['cloud.instance'].create(vals)

    def test_cloud_instance_actions_callbacks_and_backups(self):
        endpoint = self._new_endpoint(
            'Cloud Endpoint',
            CLOUD_ENDPOINT_PRODUCER,
            usage_field=self._server_usage_field(),
        )
        self._new_endpoint(
            'DNS Endpoint',
            DNS_ENDPOINT_PRODUCER,
            usage_field=self._dns_usage_field(),
        )
        server = self._new_server(endpoint=endpoint, branch='18.0', cname='srv18.example.com')
        self._new_server_module(server, 'odoo')
        custom_module = self._new_server_module(server, 'custom_a')

        zone = self._new_zone('example.com')
        zone_record = self.env['dns.zone.record'].with_context(fetching=True).create({
            'name': 'main.example.com',
            'content': 'old-target',
            'ttl': 120,
            'rtype': 'A',
            'proxied': False,
            'identifier': self._next_name('zone-rec'),
            'zone_id': zone.id,
        })
        instance = self._new_instance(server, dns_record_ids=[(4, zone_record.id)])
        second = self._new_instance(server)
        self.assertEqual(instance.http_port, 49152)
        self.assertEqual(instance.gevent_port, 49153)
        self.assertEqual(second.http_port, 49154)
        self.assertEqual(second.gevent_port, 49155)
        self.assertEqual(len(instance.uid), 12)

        instance.config = "[options]\naddons_path=/opt/odoo,/opt/custom_a\n"
        instance._compute_module_ids()
        self.assertIn(custom_module, instance.module_ids)
        instance.config = False
        instance.module_ids = self.env['cloud.server.module']
        instance._compute_module_ids()
        self.assertEqual(instance.module_ids, server.module_ids)

        instance.restart_requested = fields.Datetime.now() - timedelta(hours=1)
        instance.restarted = fields.Datetime.now()
        instance._compute_restart_requested()
        self.assertFalse(instance.restart_requested)
        self.assertEqual(
            instance._track_subtype({}),
            self.env.ref('cloud_manager.mt_field_changed'),
        )

        instance.action_deploy()
        self.assertEqual(instance.state, 'running')
        self.assertIn('addons_path', instance.config)
        instance.action_rebuild()
        self.assertEqual(instance.state, 'running')
        instance.action_stop()
        self.assertEqual(instance.state, 'exited')
        instance.action_start()
        self.assertEqual(instance.state, 'running')
        instance.action_upgrade()
        self.assertEqual(instance.upgrade, 'upgrade-log')
        instance.action_restart()
        self.assertEqual(instance.upgrade, 'upgrade-log')
        self.assertTrue(instance.restarted)
        instance.action_fshealth()
        self.assertEqual(instance.fshealth, 'fshealth-ok')
        instance.action_backup()
        self.assertTrue(instance.backup_ids)
        instance.action_reset()
        self.assertEqual(instance.state, 'running')
        instance.config = "[options]\naddons_path=/opt/odoo\n"
        instance.action_config()

        good = self.env['dns.zone.record'].with_context(fetching=True).create({
            'name': 'keep.example.com',
            'content': server.cname,
            'ttl': 120,
            'rtype': 'CNAME',
            'proxied': False,
            'identifier': self._next_name('zone-rec'),
            'zone_id': zone.id,
            'instance_id': instance.id,
        })
        instance.action_sync_urls()
        self.assertEqual(zone_record.rtype, 'CNAME')
        self.assertEqual(zone_record.content, server.cname)
        self.assertEqual(good.content, server.cname)

        action = instance.action_restore()
        self.assertEqual(action['res_model'], 'cloud.restore')
        instance.protected = True
        with self.assertRaises(ValidationError):
            instance.action_restore()
        instance.protected = False

        instance.restart_requested = fields.Datetime.now()
        instance.parse_callback({'method': 'upgrade', 'logs': 'callback logs'})
        self.assertEqual(instance.upgrade, 'callback logs')
        self.assertFalse(instance.restart_requested)
        instance.parse_callback({'method': 'restart'})

        instance.parse_backups([])
        self.assertTrue(instance.latest_backup_missing)
        instance.parse_backups([{
            'fname': 'very-old.zip',
            'timestamp': fields.Datetime.now() - timedelta(days=3),
            'trigger': 'manual',
            'source': 'default',
        }])
        self.assertTrue(instance.latest_backup_missing)
        instance.parse_backups([{
            'fname': 'fresh.zip',
            'timestamp': fields.Datetime.now(),
            'trigger': 'manual',
            'source': 'default',
        }])
        self.assertFalse(instance.latest_backup_missing)
        self.assertEqual(instance.backup_ids.mapped('name'), ['fresh.zip'])
        self.assertEqual(instance.backup_ids.source_ids.mapped('name'), ['default'])

        instance.action_remove()
        self.assertEqual(instance.state, 'removed')

    def test_cloud_instance_irpc_restrictions_and_self_restart(self):
        endpoint = self._new_endpoint(
            'Cloud Endpoint',
            CLOUD_ENDPOINT_PRODUCER,
            usage_field=self._server_usage_field(),
        )
        server = self._new_server(endpoint=endpoint, branch='18.0')
        self._new_server_module(server, 'odoo')
        instance = self._new_instance(server, is_self=True)

        with self.assertRaises(ValidationError):
            instance._irpc(method='remove', args=(instance.uid,))
        self.assertEqual(instance._irpc(method='backup', args=(instance.uid,))['backups'][0]['fname'], 'backup-latest.zip')

        instance.is_self = False
        instance.protected = True
        with self.assertRaises(ValidationError):
            instance._irpc(method='remove', args=(instance.uid,))
        self.assertTrue(instance._irpc(method='start', args=(instance.uid,)))

        instance.protected = False
        instance.is_self = True
        instance.action_restart()
        last_msg = endpoint.msg_ids.sorted('id')[-1]
        variables = safe_eval(last_msg.variables, endpoint._get_globals())
        self.assertEqual(variables['method'], 'self_upgrade')
        self.assertTrue(variables['commit_before'])

    @mute_logger('odoo.addons.cloud_manager.models.cloud_instance')
    def test_cloud_instance_invalid_config_is_ignored(self):
        endpoint = self._new_endpoint(
            'Cloud Endpoint',
            CLOUD_ENDPOINT_PRODUCER,
            usage_field=self._server_usage_field(),
        )
        server = self._new_server(endpoint=endpoint, branch='18.0')
        instance = self._new_instance(server)
        instance.config = "[options"
        instance._compute_module_ids()
        self.assertFalse(instance.module_ids)

    def test_cloud_server_parse_status_and_runtime_actions(self):
        endpoint = self._new_endpoint(
            'Cloud Endpoint',
            CLOUD_ENDPOINT_PRODUCER,
            usage_field=self._server_usage_field(),
        )
        server = self._new_server(endpoint=endpoint, branch='main')
        module_odoo = self._new_server_module(server, 'odoo')
        module_custom = self._new_server_module(server, 'custom_a')
        old_module = self._new_server_module(server, 'obsolete_module')
        stale_instance = self._new_instance(server)
        status_instance = self._new_instance(
            server,
            uid='status-uid',
            http_port=55000,
            gevent_port=55001,
            state='created',
        )
        root_disk = self.env['cloud.server.disk'].create({
            'server_id': server.id,
            'mount': '/',
            'total_gb': 1,
            'used_gb': 1,
            'free_gb': 0,
            'usage_percent': 100.0,
        })
        stale_disk = self.env['cloud.server.disk'].create({
            'server_id': server.id,
            'mount': '/old',
            'total_gb': 1,
            'used_gb': 0,
            'free_gb': 1,
            'usage_percent': 0.0,
        })

        status_obj = endpoint.produce({'method': 'status', 'args': tuple(), 'commit_before': False})['obj']
        status_obj['instances'].append({
            'uid': 'new-status-uid',
            'docker': {
                'Ports': [{'PublicPort': 54100}, {'PublicPort': 54101}],
                'State': 'running',
                'inspect': {'State': {'StartedAt': '2024-01-02T03:04:05+00:00'}},
            },
            'backups': [],
        })
        status_obj['modules'].append({
            'name': 'new_module',
            'commit': 'new-module-commit',
            'commit_date': '2024-01-02T03:04:05+00:00',
            'url': 'https://example.invalid/new_module',
            'branch': 'main',
        })
        server.parse_status(status_obj)
        self.assertEqual(server.commit, 'agent-commit')
        self.assertTrue(server.commit_date)
        parsed = server.instance_ids.filtered(lambda i: i.uid == 'status-uid')
        self.assertEqual(parsed, status_instance)
        self.assertEqual(parsed.state, 'running')
        self.assertEqual(parsed.http_port, 54000)
        self.assertEqual(parsed.gevent_port, 54001)
        self.assertTrue(server.instance_ids.filtered(lambda i: i.uid == 'new-status-uid'))
        self.assertTrue(parsed.backup_ids)
        self.assertEqual(stale_instance.state, 'removed')
        self.assertTrue(module_odoo.active)
        self.assertTrue(module_custom.active)
        self.assertTrue(server.module_ids.filtered(lambda m: m.name == 'new_module'))
        self.assertFalse(old_module.active)
        self.assertEqual(server.cpu_usage_percent, 18.4)
        self.assertEqual(server.memory_total_gb, 15.62)
        self.assertEqual(server.memory_available_gb, 8.5)
        self.assertEqual(server.memory_used_gb, 7.13)
        self.assertEqual(server.memory_usage_percent, 45.6)
        self.assertEqual(root_disk.total_gb, 98.3)
        self.assertAlmostEqual(root_disk.used_gb, 54.69)
        self.assertAlmostEqual(root_disk.free_gb, 43.62)
        self.assertTrue(server.disk_ids.filtered(lambda d: d.mount == '/data'))
        self.assertFalse(stale_disk.exists())

        with self.assertRaises(AssertionError):
            server.parse_instances({
                'instances': [{
                    'uid': 'bad-state',
                    'docker': {
                        'Ports': [{'PublicPort': 56000}, {'PublicPort': 56001}],
                        'State': 'invalid',
                        'inspect': {'State': {'StartedAt': '2024-01-02T03:04:05+00:00'}},
                    },
                    'backups': [],
                }],
            })

        self.env['cloud.server.diff'].create({'server_id': server.id, 'name': 'x...origin/main'})
        self.env['cloud.server.diff'].create({'server_id': server.id, 'name': 'y...origin/main'})
        server._compute_diff_count()
        self.assertEqual(server.diff_count, 2)

        server.ssl_renewal_pinged = False
        server._compute_ssl_renewal_ping_now()
        self.assertTrue(server.ssl_renewal_ping_now)
        server.ssl_renewal_pinged = fields.Datetime.now() - timedelta(days=6)
        server._compute_ssl_renewal_ping_now()
        self.assertTrue(server.ssl_renewal_ping_now)
        server.ssl_renewal_pinged = fields.Datetime.now()
        server._compute_ssl_renewal_ping_now()
        self.assertFalse(server.ssl_renewal_ping_now)

        server.action_ping_ssl_renewal()
        self.assertEqual(server.ssl_renewal_response, 'ssl-ok')
        server.action_agent_restart()
        self.assertTrue(server.restarted)

        to_restart = self._new_instance(server)
        to_restart.module_ids = [(6, 0, [module_odoo.id])]
        to_restart.restart_requested = fields.Datetime.now()
        self_restart = self._new_instance(server, is_self=True)
        self_restart.module_ids = [(6, 0, [module_odoo.id])]
        self_restart.restart_requested = fields.Datetime.now()
        server.action_restart_instances()
        self.assertTrue(to_restart.restarted)

        rpc_obj = server._rpc(method='echo')
        self.assertEqual(rpc_obj['method'], 'echo')
        self.assertEqual(rpc_obj['args'], tuple())
        self.assertFalse(rpc_obj['commit_before'])

    def test_passive_monitoring_endpoint_parse_hardware(self):
        endpoint = self._new_endpoint(
            'Cloud Endpoint',
            CLOUD_ENDPOINT_PRODUCER,
            usage_field=self._server_usage_field(),
        )
        monitoring = self.env.ref('cloud_manager.api_endpoint_passive_monitoring')
        monitoring.auto_commit = False

        server = self._new_server(endpoint=endpoint, cname='web-01')
        payload = {
            'host_id': 'web-01',
            'timestamp': '2026-07-11 11:00:00',
            'hardware': {
                'cpu': {
                    'usage_percent': 18.4,
                },
                'memory': {
                    'total_gb': 15.62,
                    'available_gb': 8.5,
                    'used_gb': 7.13,
                    'usage_percent': 45.6,
                },
                'disks': [{
                    'mount': '/',
                    'total_gb': 98.3,
                    'used_gb': 54.69,
                    'free_gb': 43.62,
                    'usage_percent': 55.6,
                }],
            },
        }

        globals_dict = monitoring.produce({'data': json.dumps(payload)})
        self.assertEqual(globals_dict['response'], {'status': 'OK'})
        self.assertEqual(server.cpu_usage_percent, 18.4)
        self.assertEqual(server.memory_total_gb, 15.62)
        self.assertEqual(server.disk_ids.mapped('mount'), ['/'])

        payload['host_id'] = 'missing.example.com'
        payload['hardware']['cpu']['usage_percent'] = 99.9
        monitoring.produce({'data': json.dumps(payload)})
        self.assertEqual(server.cpu_usage_percent, 18.4)

    def test_cloud_server_hardware_warning_activity(self):
        endpoint = self._new_endpoint(
            'Cloud Endpoint',
            CLOUD_ENDPOINT_PRODUCER,
            usage_field=self._server_usage_field(),
        )
        server = self._new_server(endpoint=endpoint)

        def hardware(cpu_usage, memory_usage, disk_usage):
            return {
                'cpu': {
                    'usage_percent': cpu_usage,
                },
                'memory': {
                    'total_gb': 15.62,
                    'available_gb': 8.5,
                    'used_gb': 7.13,
                    'usage_percent': memory_usage,
                },
                'disks': [{
                    'mount': '/',
                    'total_gb': 98.3,
                    'used_gb': 54.69,
                    'free_gb': 43.62,
                    'usage_percent': disk_usage,
                }],
            }

        server.parse_hardware(hardware(18.4, 45.6, 55.6))
        self.assertFalse(server._get_hardware_warning())
        self.assertFalse(server.hardware_warning)

        server.parse_hardware(hardware(91.0, 45.6, 55.6))
        self.assertTrue(server._get_hardware_warning())
        self.assertTrue(server.hardware_warning)

        warning_type = self.env.ref('mail.mail_activity_data_warning')
        warning_activities = server.activity_ids.filtered(
            lambda activity: activity.activity_type_id == warning_type and activity.user_id == server.create_uid
        )
        self.assertEqual(len(warning_activities), 1)

        server.parse_hardware(hardware(45.6, 91.0, 55.6))
        self.assertTrue(server._get_hardware_warning())
        server.parse_hardware(hardware(45.6, 45.6, 91.0))
        self.assertTrue(server._get_hardware_warning())
        server.parse_hardware(hardware(92.0, 45.6, 55.6))
        warning_activities = server.activity_ids.filtered(
            lambda activity: activity.activity_type_id == warning_type and activity.user_id == server.create_uid
        )
        self.assertEqual(len(warning_activities), 1)

        self.env['ir.config_parameter'].sudo().set_param('cloud_manager.hardware_warning_threshold_percent', '95')
        self.assertFalse(server._get_hardware_warning())

        server.status_updated = fields.Datetime.now() - timedelta(days=4)
        self.assertTrue(server._get_hardware_warning())
        self.env['ir.config_parameter'].sudo().set_param('cloud_manager.hardware_warning_stale_days', '5')
        self.assertFalse(server._get_hardware_warning())
        self.env['ir.config_parameter'].sudo().set_param('cloud_manager.hardware_warning_stale_days', '3')
        server.status_updated = fields.Datetime.now()
        server.parse_hardware(hardware(18.4, 45.6, 55.6))
        self.assertTrue(server.status_updated)
        self.assertFalse(server._get_hardware_warning())

    def test_cloud_server_diff_fetch_and_update(self):
        endpoint = self._new_endpoint(
            'Cloud Endpoint',
            CLOUD_ENDPOINT_PRODUCER,
            usage_field=self._server_usage_field(),
        )
        server = self._new_server(endpoint=endpoint, branch='main')
        module_odoo = self._new_server_module(server, 'odoo', branch='main', commit='odoo-old-commit')
        running = self._new_instance(server, state='running')
        paused = self._new_instance(server, state='paused')
        exited = self._new_instance(server, state='exited')
        for rec in (running, paused, exited):
            rec.module_ids = [(6, 0, [module_odoo.id])]

        old_diff = self.env['cloud.server.diff'].create({
            'server_id': server.id,
            'module_id': module_odoo.id,
            'name': 'old-commit...origin/main',
            'diff': 'old',
        })

        module_diff = self.env['cloud.server.diff'].create({
            'server_id': server.id,
            'module_id': module_odoo.id,
            'name': 'tmp...origin/main',
        })
        old_diff._compute_allow_update()
        module_diff._compute_name()
        self.assertTrue(module_diff.name.endswith('/main'))
        action = module_diff.action_fetch_diff()
        self.assertEqual(action['res_model'], 'cloud.server.diff')
        self.assertEqual(module_diff.diff, 'module diff')

        empty_diff = self.env['cloud.server.diff'].create({
            'server_id': server.id,
            'module_id': module_odoo.id,
            'name': 'empty-diff',
        })
        with self.assertRaises(ValidationError):
            empty_diff.action_fetch_diff()
        empty_diff.unlink()

        module_diff.update_done = True
        with self.assertRaises(ValidationError):
            module_diff.action_update_server()
        module_diff.update_done = False
        module_diff.name = f'{module_odoo.commit}...origin/{module_odoo.branch}'
        module_diff._compute_allow_update()
        self.assertTrue(module_diff.allow_update)
        module_diff.action_update_server()
        self.assertTrue(module_diff.update_done)
        self.assertEqual(module_odoo.commit, 'module-pulled')
        self.assertTrue(running.restart_requested)
        self.assertTrue(paused.restart_requested)
        self.assertFalse(exited.restart_requested)

        server_diff = self.env['cloud.server.diff'].create({
            'server_id': server.id,
            'name': 'head...origin/main',
        })
        server_action = server_diff.action_fetch_diff()
        self.assertEqual(server_action['res_model'], 'cloud.server.diff')
        self.assertEqual(server_diff.diff, 'agent diff')
        server_diff._compute_allow_update()
        self.assertTrue(server_diff.allow_update)
        server_diff.action_update_server()
        self.assertEqual(server.commit, 'agent-pulled')
        self.assertTrue(server_diff.update_done)
        self.assertTrue(server.restarted)

    def test_cloud_backup_restore_and_wizard(self):
        endpoint = self._new_endpoint(
            'Cloud Endpoint',
            CLOUD_ENDPOINT_PRODUCER,
            usage_field=self._server_usage_field(),
        )
        source_server = self._new_server(endpoint=endpoint, branch='16.0')
        target_server = self._new_server(endpoint=endpoint, branch='17.0')
        self._new_server_module(source_server, 'odoo')
        self._new_server_module(target_server, 'odoo')
        openupgrade = self._new_server_module(target_server, 'OpenUpgrade')
        source = self._new_instance(source_server)
        target = self._new_instance(target_server, state='exited')
        backup = self.env['cloud.backup'].create({
            'name': 'backup-1.zip',
            'trigger': 'manual',
            'timestamp': fields.Datetime.now(),
            'instance_id': source.id,
        })
        backup._compute_display_name()
        self.assertIn(source.name, backup.display_name)

        action = backup.action_restore()
        self.assertEqual(action['res_model'], 'cloud.restore')
        self.assertEqual(action['context']['default_backup_id'], backup.id)
        backup._restore('restore', target)
        self.assertEqual(target.upgrade, 'restore-log')

        target.module_ids = [(3, openupgrade.id)]
        with self.assertRaises(UserError):
            backup._restore('oca_migrate', target)
        target.module_ids = [(4, openupgrade.id)]

        target_server.branch = '16.0'
        with self.assertRaises(UserError):
            backup._restore('oca_migrate', target)
        target_server.branch = '17.0'
        backup._restore('oca_migrate', target)
        self.assertEqual(target.upgrade, 'migrate-log')

        wizard = self.env['cloud.restore'].create({
            'instance_id': target.id,
            'backup_id': backup.id,
            'method': 'restore',
        })
        wizard.action_restore()
        self.assertEqual(target.upgrade, 'restore-log')

    def test_dns_zone_and_record_cloudflare_flows(self):
        dns_endpoint = self._new_endpoint(
            'DNS Endpoint',
            DNS_ENDPOINT_PRODUCER,
            usage_field=self._dns_usage_field(),
        )
        zone = self._new_zone('example.com')
        zone._compute_ns_endpoint_id()
        self.assertEqual(zone.ns_endpoint_id, dns_endpoint)

        self.assertEqual(zone._search_ns_endpoint_id('=', dns_endpoint.id), [])
        self.assertEqual(zone._search_ns_endpoint_id('=', dns_endpoint.name), [])
        self.assertEqual(
            zone._search_ns_endpoint_id('=', 'no-match'),
            [('id', '=', False)],
        )
        with self.assertRaises(RuntimeError):
            zone._search_ns_endpoint_id('=', ['bad'])

        self.assertEqual(
            self.env['dns.zone'].upsert({
                'name': zone.name,
                'identifier': zone.identifier,
            }),
            zone,
        )
        created_zone = self.env['dns.zone'].upsert({
            'name': f'new-{self._next_name("zone")}.example.com',
            'identifier': self._next_name('zone-id'),
        })
        self.assertTrue(created_zone)

        existing = self.env['dns.zone.record'].with_context(fetching=True).create({
            'name': 'stale.example.com',
            'content': '9.9.9.9',
            'ttl': 120,
            'rtype': 'A',
            'proxied': False,
            'identifier': 'stale-id',
            'zone_id': zone.id,
        })

        created = self.env['dns.zone.record'].create({
            'name': 'app.example.com',
            'content': '2.2.2.2',
            'ttl': 120,
            'rtype': 'A',
            'proxied': False,
        })
        self.assertEqual(created.zone_id, zone)
        self.assertTrue(created.identifier.startswith('created-'))
        msg_count = len(dns_endpoint.msg_ids)
        created.write({'content': '2.2.2.3'})
        self.assertEqual(len(dns_endpoint.msg_ids), msg_count + 1)
        msg_count = len(dns_endpoint.msg_ids)
        created.write({'sequence': 12})
        self.assertEqual(len(dns_endpoint.msg_ids), msg_count)
        with self.assertRaises(AssertionError):
            created.write({'content': 'fail-content'})

        readonly = self.env['dns.zone.record'].with_context(fetching=True).create({
            'name': 'readonly.example.com',
            'content': '3.3.3.3',
            'ttl': 120,
            'rtype': 'A',
            'proxied': False,
            'identifier': 'readonly-id',
            'zone_id': zone.id,
            'readonly': True,
        })
        msg_count = len(dns_endpoint.msg_ids)
        readonly.cloudflare_update()
        readonly.cloudflare_create()
        readonly.cloudflare_delete()
        self.assertEqual(len(dns_endpoint.msg_ids), msg_count)

        with self.assertRaises(AssertionError):
            self.env['dns.zone.record'].create({
                'name': 'fail-create.example.com',
                'content': '4.4.4.4',
                'ttl': 120,
                'rtype': 'A',
                'proxied': False,
            })

        upserted = self.env['dns.zone.record'].with_context(fetching=True).upsert({
            'name': 'upsert.example.com',
            'content': '5.5.5.5',
            'ttl': 120,
            'rtype': 'A',
            'proxied': False,
            'identifier': 'upsert-id',
            'zone_id': zone.id,
        })
        upserted_again = self.env['dns.zone.record'].with_context(fetching=True).upsert({
            'name': 'upsert.example.com',
            'content': '5.5.5.6',
            'ttl': 120,
            'rtype': 'A',
            'proxied': False,
            'identifier': 'upsert-id',
            'zone_id': zone.id,
        })
        self.assertEqual(upserted, upserted_again)
        self.assertEqual(upserted_again.content, '5.5.5.6')

        delete_record = self.env['dns.zone.record'].with_context(fetching=True).create({
            'name': 'delete.example.com',
            'content': '6.6.6.6',
            'ttl': 120,
            'rtype': 'A',
            'proxied': False,
            'identifier': 'delete-id',
            'zone_id': zone.id,
        })
        msg_count = len(dns_endpoint.msg_ids)
        self.env['dns.zone.record'].browse(delete_record.id).unlink()
        self.assertEqual(len(dns_endpoint.msg_ids), msg_count + 1)
        skip_delete = self.env['dns.zone.record'].with_context(fetching=True).create({
            'name': 'skip-delete.example.com',
            'content': '7.7.7.7',
            'ttl': 120,
            'rtype': 'A',
            'proxied': False,
            'identifier': 'skip-delete-id',
            'zone_id': zone.id,
        })
        msg_count = len(dns_endpoint.msg_ids)
        skip_delete.with_context(fetching=True).unlink()
        self.assertEqual(len(dns_endpoint.msg_ids), msg_count)

        zone.fetch_records()
        fetched = self.env['dns.zone.record'].search([('identifier', '=', 'fetched-id')], limit=1)
        self.assertEqual(fetched.zone_id, zone)
        self.assertEqual(fetched.sequence, 1)
        self.assertFalse(existing.exists())
