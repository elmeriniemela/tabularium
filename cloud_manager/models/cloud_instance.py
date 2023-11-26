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
        comodel_name='api.endpoint',
        required=True,
        ondelete='restrict'
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
            vals['uid'] = secrets.token_hex(6)
            endpoint_id = vals.get('endpoint_id', 0)
            same = self.search([('endpoint_id', '=', endpoint_id)], order='id desc')
            vals['http_port'] = (same.http_port + 2) if same else 49152
            vals['gevent_port'] = (same.gevent_port + 2) if same else 49153

        return super().create(vals_list)

    def action_deploy(self):
        self.ensure_one()
        globals_dict = self.endpoint_id.run({
            'method': 'new_instance',
            'args': (self.name, self.uid, self.http_port, self.gevent_port),
        })
        return globals_dict.get('action', None)