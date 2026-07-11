# -*- coding: utf-8 -*-

from odoo import models, fields


class CloudServerDisk(models.Model):
    _name = 'cloud.server.disk'
    _description = 'Cloud Server Disk'
    _rec_name = 'mount'
    _order = 'server_id, mount'

    server_id = fields.Many2one(
        string="Server",
        comodel_name='cloud.server',
        required=True,
        index=True,
        ondelete='cascade',
    )

    mount = fields.Char(
        required=True,
        readonly=True,
    )

    total_gb = fields.Float(
        string="Total GB",
        digits=(16, 2),
        readonly=True,
    )

    used_gb = fields.Float(
        string="Used GB",
        digits=(16, 2),
        readonly=True,
    )

    free_gb = fields.Float(
        string="Free GB",
        digits=(16, 2),
        readonly=True,
    )

    usage_percent = fields.Float(
        readonly=True,
    )

    _uniq_mount = models.Constraint('UNIQUE(server_id, mount)', 'The disk mount must be unique within the same server.')
