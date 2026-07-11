# -*- coding: utf-8 -*-

import logging
import secrets
import os
from odoo import models, api, fields, exceptions, _
from dateutil.relativedelta import relativedelta
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
        tracking=False,
        store=True,
        compute='_compute_restart_requested',
    )

    restarted = fields.Datetime(
        tracking=False,
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
        domain=[('branch', '!=', False)],
    )

    cname = fields.Char(related="server_id.cname")

    backup_ids = fields.One2many(
        comodel_name='cloud.backup',
        inverse_name='instance_id',
        readonly=True,
    )

    latest_backup_missing = fields.Boolean(
        tracking=True,
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

    _uniq_uid = models.Constraint('UNIQUE(uid)', 'The instance uid must be unique!')
    _even_http_port = models.Constraint('CHECK(http_port % 2 = 0)', 'The HTTP port must be even!')
    _odd_gevent_port = models.Constraint('CHECK(gevent_port % 2 = 1)', 'The Gevent port must be odd!')
    _uniq_http_port = models.Constraint('UNIQUE(server_id, http_port)', 'The HTTP port must be unique within the same server!')
    _uniq_gevent_port = models.Constraint('UNIQUE(server_id, gevent_port)', 'The Gevent port must be unique within the same server!')

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
        self.message_post(body="Deployed.", subtype_xmlid="cloud_manager.mt_cloud_action")

    def action_rebuild(self):
        self.ensure_one()
        self._irpc(method='rebuild', args=(self.uid, self.http_port, self.gevent_port))
        self.state = 'running'
        self.message_post(body="Rebuilt.", subtype_xmlid="cloud_manager.mt_cloud_action")

    def action_remove(self):
        self.ensure_one()
        self._irpc(method='remove', args=(self.uid, self.http_port, self.gevent_port))
        self.state = 'removed'
        self.message_post(body="Removed.", subtype_xmlid="cloud_manager.mt_cloud_action")

    def action_stop(self):
        self.ensure_one()
        self._irpc(method='stop', args=(self.uid,))
        self.state = 'exited'
        self.message_post(body="Stopped.", subtype_xmlid="cloud_manager.mt_cloud_action")

    def action_start(self):
        self.ensure_one()
        self._irpc(method='start', args=(self.uid,))
        self.state = 'running'
        self.message_post(body="Started.", subtype_xmlid="cloud_manager.mt_cloud_action")

    def action_restart(self):
        self.ensure_one()
        if self.is_self:
            callback_url = self.env.ref('cloud_manager.endpoint_agent_callback').url
            assert callback_url
            self._irpc(method='self_upgrade', args=(self.uid, callback_url), commit_before=True)
            # Message will be posted by agent call back.
        else:
            self.action_upgrade()
            self._irpc(method='restart', args=(self.uid,))
            self.restarted = fields.Datetime.now()
            self.message_post(body="Restarted.", subtype_xmlid="cloud_manager.mt_cloud_action")

    def action_upgrade(self):
        upgrade = self._irpc(method='upgrade', args=(self.uid,))
        if upgrade:
            self.message_post(body="Upgraded.", subtype_xmlid="cloud_manager.mt_cloud_action")
            self.upgrade = upgrade


    def action_fshealth(self):
        self.fshealth = self._irpc(method='fshealth', args=(self.uid,))


    def action_backup(self):
        self.ensure_one()
        resp = self._irpc(method='backup', args=(self.uid,))
        self.message_post(body="Backup created.", subtype_xmlid="cloud_manager.mt_cloud_action")
        self.parse_backups(resp['backups'])

    def action_reset(self):
        self.ensure_one()
        self._irpc(method='reset', args=(self.uid,))
        self.state = 'running'
        self.message_post(body="Resetted.", subtype_xmlid="cloud_manager.mt_cloud_action")

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
        self.message_post(body="Config updated.", subtype_xmlid="cloud_manager.mt_cloud_action")

    def action_sync_urls(self):
        self.ensure_one()

        for rec in self.dns_record_ids:
            if rec.rtype != 'CNAME' or rec.content != self.server_id.cname:
                rec.write({
                    'rtype': 'CNAME',
                    'content': self.server_id.cname,
                })

        self._irpc(method='sync_urls', args=(self.dns_record_ids.mapped('name'), self.http_port, self.gevent_port))


    def parse_callback(self, vals):
        self.ensure_one()
        if vals.get('method') == 'upgrade':
            body = "Upgraded."
            _logger.info("Posted msg on %s", self)
            if vals.get('logs'):
                self.upgrade = vals.get('logs')
                _logger.info("Saved logs on %s", self)
                body += " Saved upgrade logs."
            self.message_post(body=body, subtype_xmlid="cloud_manager.mt_cloud_action")
            self.restart_requested = False
        if vals.get('method') == 'restart':
            self.message_post(body="Restarted.", subtype_xmlid="cloud_manager.mt_cloud_action")


    def parse_backups(self, backup_list):
        """
        [
            {
                "fname": "2026-07-10T01-02-03.pgc",
                "timestamp": "2026-07-10 01:02:03",
                "trigger": "manual",
                "source": "web-01"
            },
            {
                "fname": "2026-07-11T12-30-00.pgc",
                "timestamp": "2026-07-11 12:30:00",
                "trigger": "manual",
                "source": "web-01"
            }
        ]
        """
        self.ensure_one()
        if not backup_list:
            self.latest_backup_missing = True
            return

        Source = self.env['cloud.backup.source']
        existing_backups = {b.name: b for b in self.backup_ids}
        existing_sources = {b.name: b for b in Source.search([])}
        found = self.env['cloud.backup']
        found_sources = set()
        for backupfile in backup_list:
            fname = backupfile['fname']
            backup = existing_backups.get(fname) or found.create({
                'name': fname,
                'instance_id': self.id,
                'timestamp': backupfile['timestamp'],
                'trigger': backupfile['trigger'],
            })
            source = existing_sources.get(backupfile['source']) or Source.create({'name': backupfile['source']})
            backup.source_ids += source
            existing_backups[fname] = backup
            found += backup
            found_sources.add(source.id)

        now = fields.Datetime.now()
        check_time = now - relativedelta(hours=36)
        if max(found.mapped('timestamp'), default=now) < check_time:
            self.latest_backup_missing = True
        else:
            self.latest_backup_missing = False


        (self.backup_ids.filtered(lambda b: set(b.source_ids.ids) & found_sources) - found).unlink()

