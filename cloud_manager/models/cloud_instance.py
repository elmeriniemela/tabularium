# -*- coding: utf-8 -*-

import logging
import secrets
from odoo import models, api, fields, _

_logger = logging.getLogger(__name__)


class CloudInstance(models.Model):
    _name = 'cloud.instance'
    _description = 'Cloud Instance'
    _inherit = ['mail.thread']

    name = fields.Char(
        required=True,
        tracking=True,
    )

    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('created', 'Deployed'),
            ('restarting', 'Restarting'),
            ('running', 'Running'),
            ('paused', 'Paused'),
            ('exited', 'Exited'),
            ('dead', 'Dead'),
            ('removed', 'Removed'),
        ],
        required=True,
        tracking=True,
        default='draft',
    )

    uid = fields.Char(
        string="UID",
        readonly=True,
        required=True,
    )

    http_port = fields.Integer(
        string="HTTP Port",
        required=True,
        readonly=True,
    )

    gevent_port = fields.Integer(
        required=True,
        readonly=True,
    )

    endpoint_id = fields.Many2one(
        string="Server",
        comodel_name='api.endpoint',
        required=True,
        tracking=True,
        ondelete='restrict',
        domain=[
            ('usage_field_id.name', '=', 'endpoint_id'),
            ('usage_field_id.model_id.model', '=', 'cloud.instance'),
        ],
    )

    _sql_constraints = [
        ('uniq_uid', 'UNIQUE(uid)', 'The instance uid must be unique!'),
        ('even_http_port', 'CHECK(http_port % 2 = 0)', 'The HTTP port must be even!'),
        ('odd_gevent_port', 'CHECK(gevent_port % 2 = 1)', 'The Gevent port must be odd!'),
        ('uniq_http_port', 'UNIQUE(endpoint_id, http_port)', 'The HTTP port must be unique within the same endpoint!'),
        ('uniq_gevent_port', 'UNIQUE(endpoint_id, gevent_port)', 'The Gevent port must be unique within the same endpoint!'),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            endpoint_id = vals.get('endpoint_id', 0)
            if not vals.get('uid'):
                vals['uid'] = secrets.token_hex(6)

            same = self.search([('endpoint_id', '=', endpoint_id)], order='id desc')

            if not vals.get('http_port'):
                vals['http_port'] = (same.http_port + 2) if same else 49152

            if not vals.get('gevent_port'):
                vals['gevent_port'] = (same.gevent_port + 2) if same else 49153

        return super().create(vals_list)

    def action_deploy(self):
        self.ensure_one()
        globals_dict = self.endpoint_id.run({
            'method': 'create',
            'args': (self.uid, self.name, self.http_port, self.gevent_port),
        })
        return globals_dict.get('action', None)

    def action_remove(self):
        self.ensure_one()
        globals_dict = self.endpoint_id.run({
            'method': 'remove',
            'args': (self.uid, self.name),
        })
        return globals_dict.get('action', None)

    def action_stop(self):
        self.ensure_one()
        globals_dict = self.endpoint_id.run({
            'method': 'stop',
            'args': (self.uid,),
        })
        return globals_dict.get('action', None)

    def action_start(self):
        self.ensure_one()
        globals_dict = self.endpoint_id.run({
            'method': 'start',
            'args': (self.uid,),
        })
        return globals_dict.get('action', None)

    def action_restart(self):
        self.ensure_one()
        globals_dict = self.endpoint_id.run({
            'method': 'restart',
            'args': (self.uid,),
        })
        return globals_dict.get('action', None)


    @api.model
    def parse_status(self, endpoint, obj):
        _logger.info(obj)

        all_insts = self.with_context(active_test=False).search([('endpoint_id', '=', endpoint.id)])
        existing = {i.uid: i for i in all_insts}
        found = self.browse()
        for container in obj:
            vals = {
                'endpoint_id': endpoint.id,
                'uid': container['Names'][0].lstrip('/'),
            }
            ports = {p['PublicPort'] for p in container["Ports"]}

            for port in ports:
                if port % 2 == 0:
                    vals['http_port'] = port
                else:
                    vals['gevent_port'] = port


            state = container['State']
            assert state in {'created', 'running', 'restarting', 'exited', 'paused', 'dead'}, state
            vals['state'] = state

            inst = existing.get(vals['uid']) or self.browse()
            if inst:
                inst.write(vals)
            else:
                inst = inst.create(vals)

            found += inst

        (all_insts - found).write({'state': 'removed'})
