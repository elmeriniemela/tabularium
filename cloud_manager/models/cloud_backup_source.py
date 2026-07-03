# -*- coding: utf-8 -*-

from odoo import fields, models


class CloudBackupSource(models.Model):
    _name = 'cloud.backup.source'
    _description = 'Cloud Backup Source'
    _order = 'name'

    name = fields.Char(
        required=True,
    )

    backup_ids = fields.Many2many(
        comodel_name='cloud.backup',
        relation='cloud_backup_source_rel',
        column1='source_id',
        column2='backup_id',
    )
