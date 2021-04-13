# -*- coding: utf-8 -*-

from odoo import models, fields, api


class TogglEntry(models.Model):
    _name = 'toggl.entry'
    _description = 'Toggl Sync'
    _order = 'start desc'

    name = fields.Char(required=True)

    description = fields.Char()

    rounded_duration = fields.Float()

    duration = fields.Float(required=True, readonly=True)

    start = fields.Datetime(required=True, readonly=True)

    stop = fields.Datetime(required=True, readonly=True)

    toggl_id = fields.Integer(required=True, readonly=True)

    export_id = fields.Integer(readonly=True)

    _sql_constraints = [
        ('export_id_uniq', 'unique(export_id)', 'The export_id must be unique!'),
        ('toggl_id_uniq', 'unique(toggl_id)', 'The toggl_id must be unique!'),
    ]
