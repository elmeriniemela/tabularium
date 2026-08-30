# -*- coding: utf-8 -*-

import logging
from datetime import timedelta

import dateutil.parser
import pytz

from odoo import models, api, fields, exceptions, _

_logger = logging.getLogger(__name__)

def ptime(iso_str):
    return dateutil.parser.parse(iso_str).astimezone(pytz.utc).replace(tzinfo=None)


class CloudServer(models.Model):
    _name = 'cloud.server'
    _description = 'Cloud Server'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        required=True,
        tracking=True,
    )

    endpoint_id = fields.Many2one(
        string="Endpoint",
        comodel_name='api.endpoint',
        required=True,
        tracking=True,
        ondelete='restrict',
        domain=[
            ('usage_field_id.name', '=', 'endpoint_id'),
            ('usage_field_id.model_id.model', '=', 'cloud.server'),
        ],
    )

    ipv4_address = fields.Char(
        required=True,
        tracking=True,
        default='127.0.0.1',
    )

    cname = fields.Char(
        string="CNAME",
        required=True,
        tracking=True,
        default='localhost',
    )

    ipv6_address = fields.Char(
        required=True,
        tracking=True,
        default='0:0:0:0:0:0:0:1',
    )

    commit = fields.Char(
        tracking=True,
        readonly=True,
    )

    commit_date = fields.Datetime(
        tracking=True,
        readonly=True,
    )

    branch = fields.Char(
        tracking=True,
    )

    restarted = fields.Datetime(
        tracking=True,
        readonly=True,
    )

    instance_ids = fields.One2many(
        string="Instances",
        comodel_name='cloud.instance',
        inverse_name='server_id',
        readonly=True,
    )

    module_ids = fields.One2many(
        string="Modules",
        comodel_name='cloud.server.module',
        inverse_name='server_id',
        readonly=False,
    )

    diff_ids = fields.One2many(
        comodel_name='cloud.server.diff',
        inverse_name='server_id',
    )

    diff_count = fields.Integer(
        compute='_compute_diff_count'
    )

    ssl_renewal_ping_now = fields.Boolean(
        string="SSL Renewal Ping Now",
        compute='_compute_ssl_renewal_ping_now',
    )

    ssl_renewal_pinged = fields.Datetime(
        string="SSL Renewal Pinged",
        tracking=True,
        readonly=True,
    )

    ssl_renewal_response = fields.Text(
        string="SSL Renewal Response",
        readonly=True,
    )

    cpu_usage_percent = fields.Float(
        string="CPU Usage (%)",
        readonly=True,
    )

    memory_total_gb = fields.Float(
        string="Memory Total GB",
        digits=(16, 2),
        readonly=True,
    )

    memory_available_gb = fields.Float(
        string="Memory Available GB",
        digits=(16, 2),
        readonly=True,
    )

    memory_used_gb = fields.Float(
        string="Memory Used GB",
        digits=(16, 2),
        readonly=True,
    )

    memory_usage_percent = fields.Float(
        string="Memory Usage (%)",
        readonly=True,
    )

    disk_ids = fields.One2many(
        string="Disks",
        comodel_name='cloud.server.disk',
        inverse_name='server_id',
        readonly=True,
    )

    status_updated = fields.Datetime(
        readonly=True,
    )

    hardware_warning = fields.Text(
        string="Hardware Warning",
        compute='_compute_hardware_warning',
    )


    _uniq_name = models.Constraint('UNIQUE(name)', 'Server name should be unique.')

    @api.depends('diff_ids')
    def _compute_diff_count(self):
        for record in self:
            record.diff_count = len(record.diff_ids)


    def _compute_ssl_renewal_ping_now(self):
        for record in self:
            if not record.ssl_renewal_pinged:
                record.ssl_renewal_ping_now = True
            else:
                record.ssl_renewal_ping_now = (fields.Datetime.now() - record.ssl_renewal_pinged).days > 5

    @api.depends('cpu_usage_percent', 'memory_usage_percent', 'disk_ids.usage_percent', 'status_updated')
    def _compute_hardware_warning(self):
        for record in self:
            record.hardware_warning = record._get_hardware_warning()


    def action_ping_ssl_renewal(self):
        self.ssl_renewal_response = self._rpc(method='ssl_renew')
        self.ssl_renewal_pinged = fields.Datetime.now()


    def action_agent_restart(self):
        self.ensure_one()
        self._rpc(method='agent_restart')
        self.restarted = fields.Datetime.now()

    def action_restart_instances(self):
        instances = self.instance_ids.filtered(lambda i: i.restart_requested)
        norm = instances.filtered(lambda i: not i.is_self)
        for n in norm: n.action_restart()
        for i in (instances - norm): i.action_restart()


    def _rpc(self, **kwargs):
        self.ensure_one()
        if 'args' not in kwargs:
            kwargs['args'] = tuple()
        if 'commit_before' not in kwargs:
            kwargs['commit_before'] = False
        return self.endpoint_id.produce(kwargs).get('obj')

    def parse_status(self, obj):
        self.ensure_one()
        self.status_updated = obj['timestamp']
        self.commit = obj['agent']['commit']
        self.commit_date = ptime(obj['agent']['commit_date'])
        self.parse_instances(obj)
        self.parse_modules(obj)
        self.parse_hardware(obj['hardware'])

    def parse_instances(self, obj):
        def docker_vals(container):
            vals = {}
            ports = {p['PublicPort'] for p in container["Ports"]}

            for port in ports:
                if port % 2 == 0:
                    vals['http_port'] = port
                else:
                    vals['gevent_port'] = port


            state = container['State']
            assert state in {'created', 'running', 'restarting', 'exited', 'paused', 'dead'}, state
            vals['state'] = state
            vals['restarted'] = dateutil.parser.isoparse(container['inspect']['State']['StartedAt']).replace(tzinfo=None)
            return vals


        all_insts = self.instance_ids

        existing = {i.uid: i for i in all_insts}
        found = self.env['cloud.instance'].browse()
        _logger.info("Parse %s containers.", len(obj))
        for cloud in obj['instances']:
            uid = cloud['uid']
            inst = existing.get(uid) or self.env['cloud.instance'].browse()
            vals = {
                'server_id': self.id,
                'uid': uid,
            }
            vals.update(docker_vals(cloud['docker']))

            if inst:
                inst.write(vals)
            else:
                inst = inst.with_context(default_name=uid).create(vals)

            inst.parse_backups(cloud['backups'])
            found += inst

        (all_insts - found).write({'state': 'removed'})

    def parse_modules(self, obj):
        Module = self.env['cloud.module']
        all_modules = self.with_context(active_test=False).module_ids
        existing_mods = {m.name: m for m in all_modules}

        found_mods = all_modules.browse()
        for mod in obj['modules']:
            name = mod['name']
            vals = {
                'server_id': self.id,
                'module_id': (Module.search([('name', '=', name)]) or Module.create({'name': name})).id,
                'commit': mod['commit'],
                'commit_date': ptime(mod['commit_date']),
                'url': mod['url'],
                'branch': mod['branch'],
                'active': True,
            }

            module = existing_mods.get(name) or all_modules.browse()
            if module:
                module.write(vals)
            else:
                module = module.create(vals)
            found_mods += module

        (all_modules - found_mods).active = False


    def _get_hardware_warning(self):
        self.ensure_one()
        threshold = float(self.env['ir.config_parameter'].sudo().get_param('cloud_manager.hardware_warning_threshold_percent', 90))
        stale_days = int(self.env['ir.config_parameter'].sudo().get_param('cloud_manager.hardware_warning_stale_days', 3))
        metrics = []
        warnings = []

        if self.cpu_usage_percent > threshold:
            metrics.append(_("CPU %(usage).1f%%", usage=self.cpu_usage_percent))
        if self.memory_usage_percent > threshold:
            metrics.append(_("Memory %(usage).1f%%", usage=self.memory_usage_percent))
        for disk in self.disk_ids:
            if disk.usage_percent > threshold:
                metrics.append(_("Disk %(mount)s %(usage).1f%%", mount=disk.mount, usage=disk.usage_percent))
        if self.status_updated and fields.Datetime.now() - self.status_updated > timedelta(days=stale_days):
            warnings.append(_("Hardware status has not been updated for more than %(days)s days.", days=stale_days))

        if metrics:
            warnings.append(_(
                "Hardware usage is above %(threshold).1f%%: %(metrics)s",
                threshold=threshold,
                metrics=", ".join(metrics),
            ))
        if not warnings:
            return False

        return "\n".join(warnings)

    def _update_hardware_warning_activity(self, warning):
        self.ensure_one()
        activity_type = self.env.ref('mail.mail_activity_data_warning')
        existing_activity = self.activity_ids.filtered(
            lambda activity: activity.activity_type_id == activity_type and activity.user_id == self.create_uid
        )
        if warning and not existing_activity:
            self.activity_schedule(
                'mail.mail_activity_data_warning',
                note=warning,
                user_id=self.create_uid.id,
            )
        elif not warning and existing_activity:
            existing_activity.unlink()


    def parse_hardware(self, hw_dict):
        """
        "cpu": {
            "usage_percent": 18.4
        },
        "memory": {
            "total_gb": 15.62,
            "available_gb": 8.5,
            "used_gb": 7.13,
            "usage_percent": 45.6
        },
        "disks": [
            {
                "mount": "/",
                "total_gb": 98.3,
                "used_gb": 54.69,
                "free_gb": 43.62,
                "usage_percent": 55.6
            }
        ]
        """
        self.ensure_one()
        memory = hw_dict['memory']
        self.write({
            'cpu_usage_percent': hw_dict['cpu']['usage_percent'],
            'memory_total_gb': memory['total_gb'],
            'memory_available_gb': memory['available_gb'],
            'memory_used_gb': memory['used_gb'],
            'memory_usage_percent': memory['usage_percent'],
        })

        all_disks = self.disk_ids
        existing_disks = {disk.mount: disk for disk in all_disks}

        found_disks = all_disks.browse()
        for disk in hw_dict['disks']:
            mount = disk['mount']
            vals = {
                'server_id': self.id,
                'mount': mount,
                'total_gb': disk['total_gb'],
                'used_gb': disk['used_gb'],
                'free_gb': disk['free_gb'],
                'usage_percent': disk['usage_percent'],
            }

            disk_record = existing_disks.get(mount) or all_disks.browse()
            if disk_record:
                disk_record.write(vals)
            else:
                disk_record = disk_record.create(vals)
            found_disks += disk_record

        (all_disks - found_disks).unlink()

        self.env.flush_all()
        self.invalidate_recordset(['disk_ids'])
        warning = self._get_hardware_warning()
        self._update_hardware_warning_activity(warning)
