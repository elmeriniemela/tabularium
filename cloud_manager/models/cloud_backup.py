# -*- coding: utf-8 -*-

import logging
from odoo import models, api, fields, exceptions, _

_logger = logging.getLogger(__name__)


class CloudBackup(models.Model):
    _name = 'cloud.backup'
    _description = 'Cloud Backup'
    _inherit = ['mail.thread']

    name = fields.Char(
        required=True,
        tracking=True,
        readonly=True,
    )

    timestamp = fields.Datetime(
        required=True,
        tracking=True,
        readonly=True,
    )

    instance_id = fields.Many2one(
        comodel_name='cloud.instance',
        required=True,
        tracking=True,
        readonly=True,
        ondelete='cascade',
    )

    _sql_constraints = [
        ('uniq_name', 'UNIQUE(instance_id, name)', 'Backup name should be unique within an instance!'),
    ]

    @api.depends('instance_id', 'name')
    def _compute_display_name(self):
        for record in self:
            record.display_name = f'{record.instance_id.name}: {record.name}'


    def action_restore(self):
        action = self.env['ir.actions.act_window']._for_xml_id('cloud_manager.cloud_restore_action')
        action['context'] = {'default_backup_id': self.id}
        return action


    def _restore(self, dst_instance):
        self.ensure_one()
        globals_dict = dst_instance.endpoint_id.produce({
            'method': 'restore',
            'args': (self.instance_id.uid, dst_instance.uid, self.name),
        })
        self.message_post(body="Restored to %s on server %s." % (dst_instance.display_name, dst_instance.endpoint_id.display_name))
        return globals_dict.get('action', None)
