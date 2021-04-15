# -*- coding: utf-8 -*-

import json
from odoo import models, fields, api
import re


class TogglTask(models.Model):
    _name = 'toggl.task'
    _description = 'Toggl Task'
    _order = 'task_id desc'

    task_id = fields.Integer(required=True, readonly=True)

    name = fields.Char(required=True, readonly=True)

    invoicable = fields.Boolean()

    _sql_constraints = [
        ('task_id_uniq', 'unique(task_id)', 'The task_id must be unique!'),
    ]


class TogglEntry(models.Model):
    _name = 'toggl.entry'
    _description = 'Toggl Sync'
    _order = 'start desc'

    name = fields.Char(required=True)

    toggl_name = fields.Char(required=True)

    description = fields.Char()

    rounded_duration = fields.Float()

    dirty = fields.Boolean(compute='_compute_dirty')

    date = fields.Date(compute='_compute_date', store=True)

    total_duration = fields.Float(compute='_compute_total_duration', store=True)

    duration = fields.Float(required=True, readonly=True)

    start = fields.Datetime(required=True, readonly=True)

    stop = fields.Datetime(required=True, readonly=True)

    toggl_id = fields.Integer(required=True, readonly=True)

    export_id = fields.Integer(readonly=True)

    task_id = fields.Many2one(
        comodel_name='toggl.task',
        compute='_compute_task_id',
        store=True,
        readonly=True,
    )

    parent_id = fields.Many2one(
        comodel_name='toggl.entry',
        compute='_compute_parent_id',
        store=True,
        readonly=True,
    )

    child_ids = fields.One2many(
        comodel_name='toggl.entry',
        inverse_name='parent_id',
        readonly=True,
    )


    _sql_constraints = [
        ('export_id_uniq', 'unique(export_id)', 'The export_id must be unique!'),
        ('toggl_id_uniq', 'unique(toggl_id)', 'The toggl_id must be unique!'),
    ]

    @api.depends('duration', 'child_ids.duration')
    def _compute_total_duration(self):
        for record in self:
            record.total_duration = record.duration + sum(record.child_ids.mapped('duration'))

    @api.depends('name')
    def _compute_task_id(self):
        Task = self.env['toggl.task']
        for record in self:
            ids = [int(m) for m in re.findall('\[(\d+)\]', record.name)]
            if ids:
                [task_id] = ids
                record.task_id = Task.search([('task_id', '=', task_id)], limit=1) \
                    or Task.create({
                        'name': record.name,
                        'task_id': task_id
                    })
            else:
                record.task_id = False

    @api.depends('date', 'task_id', 'name')
    def _compute_parent_id(self):
        for record in self:
            if record.child_ids:
                record.parent_id = False
                continue

            record.parent_id = record.search([
                ('date', '=', record.date),
                ('id', '!=', record._origin.id),
                '|',
                ('task_id', '=', record.task_id.id),
                ('name', '=', record.name),
            ], limit=1)


    @api.depends('name', 'toggl_name')
    def _compute_dirty(self):
        for record in self:
            record.dirty = record.name != record.toggl_name

    @api.depends('start')
    def _compute_date(self):
        for record in self:
            record.date = record.start.date()

    def push_toggl(self):
        for record in self:
            record.env['toggl'].update_time_entry(
                time_entry_id=record.toggl_id,
                json={'time_entry': {'description': record.name}}
            )
            record.toggl_name = record.name
