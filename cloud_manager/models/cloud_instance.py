# -*- coding: utf-8 -*-

import logging
import secrets
import os
from odoo import models, api, fields, exceptions, _
from odoo.exceptions import ValidationError
import configparser as ConfigParser

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

    restart_requested = fields.Datetime(
        tracking=True,
        store=True,
        compute='_compute_restart_requested',
    )

    restarted = fields.Datetime(
        tracking=True,
        readonly=True,
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

    is_self = fields.Boolean(
        tracking=True,
    )

    config = fields.Text()

    upgrade = fields.Text()

    fshealth = fields.Text(
        string="Filestore Health",
    )


    server_id = fields.Many2one(
        string="Server",
        comodel_name='cloud.server',
        required=True,
        tracking=True,
        index=True,
        ondelete='restrict',
    )

    cname = fields.Char(related="server_id.cname")

    backup_ids = fields.One2many(
        comodel_name='cloud.backup',
        inverse_name='instance_id',
        readonly=True,
    )

    module_ids = fields.Many2many(
        string="Modules",
        comodel_name='cloud.server.module',
        domain="[('server_id', '=', server_id)]",
        compute='_compute_module_ids',
        store=True,
        readonly=False,
        required=True,
    )

    dns_record_ids = fields.One2many(
        string="DNS Records",
        comodel_name='dns.zone.record',
        inverse_name='instance_id',
        required=True,
    )

    _sql_constraints = [
        ('uniq_uid', 'UNIQUE(uid)', 'The instance uid must be unique!'),
        ('even_http_port', 'CHECK(http_port % 2 = 0)', 'The HTTP port must be even!'),
        ('odd_gevent_port', 'CHECK(gevent_port % 2 = 1)', 'The Gevent port must be odd!'),
        ('uniq_http_port', 'UNIQUE(server_id, http_port)', 'The HTTP port must be unique within the same server!'),
        ('uniq_gevent_port', 'UNIQUE(server_id, gevent_port)', 'The Gevent port must be unique within the same server!'),
    ]

    @api.depends('server_id', 'config')
    def _compute_module_ids(self):
        for record in self:
            if record.config:
                parser = ConfigParser.RawConfigParser()
                try:
                    parser.read_string(record.config)
                except Exception as error:
                    _logger.exception(error)
                    continue
                module_names = [os.path.basename(p.strip()) for p in parser.get('options', 'addons_path', fallback='').split(',')]
                module_names.append('odoo')
                record.module_ids = record.server_id.module_ids.filtered(lambda m: m.name in module_names)
            else:
                record.module_ids = record.module_ids or record.server_id.module_ids

    @api.depends('restarted')
    def _compute_restart_requested(self):
        for record in self:
            if not record.restart_requested:
                continue

            if record.restarted >= record.restart_requested:
                record.restart_requested = False

    def _track_subtype(self, initial_values):
        """ Give the subtypes triggered by the changes on the record according
        to values that have been updated.

        :param dict initial_values: original values of the record; only modified
          fields are present in the dict

        :returns: a subtype browse record or False if no subtype is triggered
        """
        self.ensure_one()
        return self.env.ref('cloud_manager.mt_field_changed')

    def _irpc(self, **kwargs):
        method = kwargs['method']
        is_self_allowed = [
            'restart',
            'backup',
            'config',
            'upgrade',
            'fshealth',
            'self_upgrade',
            'sync_urls',
        ]
        if self.is_self and method not in is_self_allowed:
            raise exceptions.ValidationError(_("This action can't be performed on self."))

        is_protected_allowed = [
            'rebuild',
            'start',
            'stop',
        ] + is_self_allowed

        if self.protected and method not in is_protected_allowed:
            raise exceptions.ValidationError(_("Unable to proceed with the action. This server is protected."))

        return self.server_id._rpc(**kwargs)


    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            server_id = vals.get('server_id', 0)
            if not vals.get('uid'):
                vals['uid'] = secrets.token_hex(6)

            same = self.search([('server_id', '=', server_id)], order='id desc', limit=1)

            if not vals.get('http_port'):
                vals['http_port'] = (same.http_port or 49150) + 2

            if not vals.get('gevent_port'):
                vals['gevent_port'] = (same.gevent_port or 49151) + 2

        return super().create(vals_list)

    def action_deploy(self):
        self.ensure_one()
        self.config = self._irpc(method='create', args=(self.uid, self.dns_record_ids.mapped('name'), self.http_port, self.gevent_port, self.module_ids.mapped('name')))
        self.state = 'running'

    def action_rebuild(self):
        self.ensure_one()
        self._irpc(method='rebuild', args=(self.uid, self.http_port, self.gevent_port))
        self.state = 'running'
        self.message_post(body="Rebuilt.")

    def action_remove(self):
        self.ensure_one()
        self._irpc(method='remove', args=(self.uid, self.http_port, self.gevent_port))
        self.state = 'removed'

    def action_stop(self):
        self.ensure_one()
        self._irpc(method='stop', args=(self.uid,))
        self.state = 'exited'

    def action_start(self):
        self.ensure_one()
        self._irpc(method='start', args=(self.uid,))
        self.state = 'running'

    def action_restart(self):
        self.ensure_one()
        if self.is_self:
            callback_url = self.env.ref('cloud_manager.endpoint_agent_callback').url
            assert callback_url
            self._irpc(method='self_upgrade', args=(self.uid, callback_url), commit_before=True)
        else:
            self.action_upgrade()
            self._irpc(method='restart', args=(self.uid,))
            self.restarted = fields.Datetime.now()

    def action_upgrade(self):
        upgrade = self._irpc(method='upgrade', args=(self.uid,))
        if upgrade:
            self.message_post(body="Upgraded.")
            self.upgrade = upgrade


    def action_fshealth(self):
        self.fshealth = self._irpc(method='fshealth', args=(self.uid,))


    def action_backup(self):
        self.ensure_one()
        resp = self._irpc(method='backup', args=(self.uid,))
        self.message_post(body="Backup created.")
        self.parse_backups(resp['backups'])

    def action_reset(self):
        self.ensure_one()
        self._irpc(method='reset', args=(self.uid,))
        self.state = 'running'
        self.message_post(body="Resetted.")

    def action_restore(self):
        self.ensure_one()
        if self.protected:
            raise exceptions.ValidationError(_("Unable to proceed with the action. This server is protected."))

        action = self.env['ir.actions.act_window']._for_xml_id('cloud_manager.cloud_restore_action')
        action['context'] = {'default_instance_id': self.id}
        return action

    def action_config(self):
        self.ensure_one()
        self._irpc(method='config', args=(self.uid, self.config))
        self.message_post(body="Config updated.")

    def action_sync_urls(self):
        self.ensure_one()

        for rec in self.dns_record_ids:
            if rec.rtype != 'CNAME' or rec.content != self.server_id.cname:
                rec.write({
                    'rtype': 'CNAME',
                    'content': self.server_id.cname,
                })

        self._irpc(method='sync_urls', args=(self.uid, self.dns_record_ids.mapped('name'), self.http_port, self.gevent_port))


    def parse_callback(self, vals):
        self.ensure_one()
        if vals.get('method') == 'upgrade':
            self.message_post(body="Upgraded.")
            _logger.info("Posted msg on %s", self)
            if vals.get('logs'):
                self.upgrade = vals.get('logs')
                _logger.info("Saved logs on %s", self)
            self.restart_requested = False


    def parse_backups(self, backup_list):
        self.ensure_one()
        existing = {b.name: b for b in self.backup_ids}
        found = self.env['cloud.backup']

        for backupfile in backup_list:
            fname = backupfile['fname']
            backup = existing.get(fname) or found.create({
                'name': fname,
                'instance_id': self.id,
                'timestamp': backupfile['timestamp'],
                'trigger': backupfile['trigger'],
            })
            existing[fname] = backup
            found += backup

        (self.backup_ids - found).unlink()
