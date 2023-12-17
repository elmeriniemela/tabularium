# -*- coding: utf-8 -*-

import logging
import secrets
from odoo import models, api, fields, exceptions, _
from odoo.exceptions import ValidationError

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

    protected = fields.Boolean(
        tracking=True,
    )

    config = fields.Text()

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

    backup_ids = fields.One2many(
        comodel_name='cloud.backup',
        inverse_name='instance_id',
        readonly=True,
    )

    _sql_constraints = [
        ('uniq_uid', 'UNIQUE(uid)', 'The instance uid must be unique!'),
        ('even_http_port', 'CHECK(http_port % 2 = 0)', 'The HTTP port must be even!'),
        ('odd_gevent_port', 'CHECK(gevent_port % 2 = 1)', 'The Gevent port must be odd!'),
        ('uniq_http_port', 'UNIQUE(endpoint_id, http_port)', 'The HTTP port must be unique within the same endpoint!'),
        ('uniq_gevent_port', 'UNIQUE(endpoint_id, gevent_port)', 'The Gevent port must be unique within the same endpoint!'),
    ]

    def _track_subtype(self, initial_values):
        """ Give the subtypes triggered by the changes on the record according
        to values that have been updated.

        :param dict initial_values: original values of the record; only modified
          fields are present in the dict

        :returns: a subtype browse record or False if no subtype is triggered
        """
        self.ensure_one()
        return self.env.ref('cloud_manager.mt_field_changed')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            endpoint_id = vals.get('endpoint_id', 0)
            if not vals.get('uid'):
                vals['uid'] = secrets.token_hex(6)

            same = self.search([('endpoint_id', '=', endpoint_id)], order='id desc', limit=1)

            if not vals.get('http_port'):
                vals['http_port'] = (same.http_port + 2) if same else 49152

            if not vals.get('gevent_port'):
                vals['gevent_port'] = (same.gevent_port + 2) if same else 49153

        return super().create(vals_list)

    def action_deploy(self):
        self.ensure_one()
        globals_dict = self.endpoint_id.produce({
            'method': 'create',
            'args': (self.uid, self.name, self.http_port, self.gevent_port),
        })
        self.state = 'running'
        self.config = globals_dict.get('obj', False)
        return globals_dict.get('action', None)

    def action_remove(self):
        self.ensure_one()
        if self.protected:
            raise exceptions.ValidationError(_("Unable to proceed with the action. This server is protected."))
        globals_dict = self.endpoint_id.produce({
            'method': 'remove',
            'args': (self.uid, self.name),
        })
        self.state = 'removed'
        return globals_dict.get('action', None)

    def action_stop(self):
        self.ensure_one()
        globals_dict = self.endpoint_id.produce({
            'method': 'stop',
            'args': (self.uid,),
        })
        self.state = 'exited'
        return globals_dict.get('action', None)

    def action_start(self):
        self.ensure_one()
        globals_dict = self.endpoint_id.produce({
            'method': 'start',
            'args': (self.uid,),
        })
        self.state = 'running'
        return globals_dict.get('action', None)

    def action_restart(self):
        self.ensure_one()
        globals_dict = self.endpoint_id.produce({
            'method': 'restart',
            'args': (self.uid,),
        })
        self.message_post(body="Restarted.")
        return globals_dict.get('action', None)

    def action_backup(self):
        self.ensure_one()
        globals_dict = self.endpoint_id.produce({
            'method': 'backup',
            'args': (self.uid,),
        })
        self.message_post(body="Backup created.")
        return globals_dict.get('action', None)

    def action_reset(self):
        self.ensure_one()
        if self.protected:
            raise exceptions.ValidationError(_("Unable to proceed with the action. This server is protected."))
        globals_dict = self.endpoint_id.produce({
            'method': 'reset',
            'args': (self.uid,),
        })
        self.state = 'running'
        self.message_post(body="Resetted.")
        return globals_dict.get('action', None)

    def action_config(self):
        self.ensure_one()
        globals_dict = self.endpoint_id.produce({
            'method': 'config',
            'args': (self.uid, self.config),
        })
        self.message_post(body="Config updated.")
        return globals_dict.get('action', None)


    def parse_backups(self, backup_list):
        self.ensure_one()
        existing = {b.name: b for b in self.backup_ids}
        found = self.env['could.backup']

        for backupfile in backup_list:
            fname = backupfile['fname']
            backup = existing.get(fname) or found.create({
                'name': fname,
                'instance_id': self.id,
            })
            existing[fname] = backup
            found += backup

        (self.backup_ids - found).unlink()

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



        all_insts = self.with_context(active_test=False).search([('endpoint_id', '=', endpoint.id)])
        existing = {i.uid: i for i in all_insts}
        found = self.browse()
        _logger.info("Parse %s containers.", len(obj))
        for cloud in obj:
            uid = cloud['uid']
            inst = existing.get(uid) or self.browse()
            vals = {
                'endpoint_id': endpoint.id,
                'uid': uid,
            }
            vals.update(docker_vals(vals['docker']))

            if inst:
                inst.write(vals)
            else:
                inst = inst.create(vals)

            inst.parse_backups(vals['backups'])
            found += inst

        (all_insts - found).write({'state': 'removed'})
