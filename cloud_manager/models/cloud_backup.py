# -*- coding: utf-8 -*-

import logging
from odoo import models, api, fields, exceptions, _

_logger = logging.getLogger(__name__)


class CloudBackup(models.Model):
    _name = 'cloud.backup'
    _description = 'Cloud Backup'
    _inherit = ['mail.thread']
    _order = 'instance_id, timestamp desc'
    _rec_name = 'display_name'

    name = fields.Char(
        required=True,
        tracking=True,
    )

    trigger = fields.Char(
        required=True,
        tracking=True,
    )

    timestamp = fields.Datetime(
        required=True,
        tracking=True,
    )

    instance_id = fields.Many2one(
        comodel_name='cloud.instance',
        required=True,
        tracking=True,
        ondelete='cascade',
    )

    display_name = fields.Char(
        compute="_compute_display_name",
        store=True,
    )

    _sql_constraints = [
        ('uniq_name', 'UNIQUE(instance_id, name)', 'Backup name should be unique within an instance!'),
    ]

    @api.depends('name', 'instance_id.name')
    def _compute_display_name(self):
        for record in self:
            record.display_name = f'{record.instance_id.name}: {record.name}'


    def action_restore(self):
        action = self.env['ir.actions.act_window']._for_xml_id('cloud_manager.cloud_restore_action')
        action['context'] = {
            'default_instance_id': self.instance_id.id,
            'default_backup_id': self.id,
        }
        return action


    def _restore(self, method, dst_instance):
        self.ensure_one()
        if method == 'oca_migrate':
            if 'OpenUpgrade' not in dst_instance.module_ids.mapped('name'):
                # Check if the instance has OpenUpgrade module installed
                raise exceptions.UserError(_("You can only use OCA Migrate method with OpenUpgrade installed."))
            if not (float(dst_instance.server_id.branch) > float(self.instance_id.server_id.branch)):
                raise exceptions.UserError(_("Destination server should have higher branch than src: %s is not greater than %s.") %
                                           (dst_instance.server_id.branch, self.instance_id.server_id.branch))
        resp = dst_instance._irpc(method=method, args=(self.instance_id.uid, dst_instance.uid, self.trigger, self.name))
        if resp:
            dst_instance.message_post(body="Migraded from %s to %s." % (self.instance_id.server_id.branch, dst_instance.server_id.branch))
            dst_instance.upgrade = resp
        self.message_post(body="Restored to %s on server %s using method '%s'." % (dst_instance.display_name, dst_instance.server_id.display_name, method))