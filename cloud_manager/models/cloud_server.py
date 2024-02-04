# -*- coding: utf-8 -*-

import logging
from odoo import models, api, fields, exceptions, _

_logger = logging.getLogger(__name__)


class CloudServer(models.Model):
    _name = 'cloud.server'
    _description = 'Cloud Server'
    _inherit = ['mail.thread']

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

    commit = fields.Char(
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
        comodel_name='cloud.instance',
        inverse_name='server_id',
    )

    diff_ids = fields.One2many(
        comodel_name='cloud.server.diff',
        inverse_name='server_id',
    )

    diff_count = fields.Integer(
        compute='_compute_diff_count'
    )


    _sql_constraints = [
        ('uniq_name', 'UNIQUE(name)', 'Server name should be unique.'),
    ]

    @api.depends('diff_ids')
    def _compute_diff_count(self):
        for record in self:
            record.diff_count = len(record.diff_ids)

    def action_agent_restart(self):
        self.ensure_one()
        self._rpc(method='agent_restart')
        self.restarted = fields.Datetime.now()

    def action_restart_instances(self):
        instances = self.instance_ids.filtered(lambda i: i.restart_needed)
        norm = instances.filtered(lambda i: not i.is_self)
        for n in norm: n.action_restart()
        for i in (instances - norm): i.action_restart()


    def _rpc(self, **kwargs):
        self.ensure_one()
        if 'args' not in kwargs:
            kwargs['args'] = tuple()
        return self.endpoint_id.produce(kwargs)['obj']

    @api.model
    def parse_status(self, endpoint, obj):

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
            return vals



        server = self.with_context(active_test=False).search([('endpoint_id', '=', endpoint.id)])
        server.commit = obj['agent']['commit']

        all_insts = server.instance_ids

        existing = {i.uid: i for i in all_insts}
        found = self.env['cloud.instance'].browse()
        _logger.info("Parse %s containers.", len(obj))
        for cloud in obj['instances']:
            uid = cloud['uid']
            inst = existing.get(uid) or self.env['cloud.instance'].browse()
            vals = {
                'server_id': server.id,
                'uid': uid,
            }
            vals.update(docker_vals(cloud['docker']))

            if inst:
                inst.write(vals)
            else:
                inst = inst.create(vals)

            inst.parse_backups(cloud['backups'])
            found += inst

        (all_insts - found).write({'state': 'removed'})

