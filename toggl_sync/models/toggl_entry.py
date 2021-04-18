# -*- coding: utf-8 -*-

import json
from odoo import models, fields, api, _
import re
import xmlrpc.client
import urllib.parse
from odoo.exceptions import UserError
import math


class TogglTask(models.Model):
    _name = 'toggl.task'
    _description = 'Toggl Task'
    _order = 'task_id desc'

    task_id = fields.Integer(required=True, readonly=True)

    project_id = fields.Integer(required=True, readonly=True)

    name = fields.Char(required=True, readonly=True)

    invoicable = fields.Boolean()

    entry_ids = fields.One2many(
        comodel_name='toggl.entry',
        inverse_name='task_id',
        readonly=True,
    )

    _sql_constraints = [
        ('task_id_uniq', 'unique(task_id)', 'The task_id must be unique!'),
    ]

    def fetch(self):
        url = self.env['ir.config_parameter'].sudo().get_param('toggl.export.url')
        dbname = self.env['ir.config_parameter'].sudo().get_param('toggl.export.dbname')
        username = self.env['ir.config_parameter'].sudo().get_param('toggl.export.username')
        pwd = self.env['ir.config_parameter'].sudo().get_param('toggl.export.pwd')

        if not all([url, dbname, username, pwd]):
            raise UserError(_("Export credentials not configured."))


        server_common = xmlrpc.client.ServerProxy(urllib.parse.urljoin(url, '/xmlrpc/common'))
        uid = server_common.authenticate(dbname, username, pwd, {})
        server_models = xmlrpc.client.ServerProxy(urllib.parse.urljoin(url, '/xmlrpc/object'))

        for record in self:
            task_res = server_models.execute_kw(dbname, uid, pwd,
                'project.task', 'search_read',
                [[
                    ['id', '=', record.task_id]
                ]],
                {'fields': ['sale_line_id', 'project_id'], 'limit': 1}
            )
            if not task_res:
                record.invoicable = False
                continue

            task_res = task_res[0]
            record.project_id, name = task_res['project_id']

            if not task_res['sale_line_id']:
                record.invoicable = False
                continue

            sale_line_id, name = task_res['sale_line_id']
            sale_line_res = server_models.execute_kw(dbname, uid, pwd,
                'sale.order.line', 'search_read',
                [[
                    ['id', '=', sale_line_id]
                ]],
                {'fields': ['price_unit'], 'limit': 1}
            )

            if not sale_line_res:
                record.invoicable = False
                continue

            sale_line_res = sale_line_res[0]

            record.invoicable = sale_line_res['price_unit'] > 0.0

    def write(self, vals):
        "TODO: for some reason the depends does not work."
        res = super().write(vals)
        if 'invoicable' in vals:
            self.mapped('entry_ids')._compute_rounded_duration()
        return res

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        try:
            with records.env.cr.savepoint():
                records.fetch()
        except Exception as error:
            _logger.exception(error)
        return records


class TogglEntry(models.Model):
    _name = 'toggl.entry'
    _description = 'Toggl Entry'
    _order = 'start desc'

    name = fields.Char(required=True)

    toggl_name = fields.Char(required=True)

    description = fields.Char()

    rounded_duration = fields.Float(compute='_compute_rounded_duration', store=True)

    dirty = fields.Boolean(compute='_compute_dirty')

    date = fields.Date(compute='_compute_date', store=True)

    total_duration = fields.Float(compute='_compute_total_duration', store=True)

    duration = fields.Float(required=True, readonly=True)

    start = fields.Datetime(required=True, readonly=True)

    stop = fields.Datetime(required=True, readonly=True)

    toggl_id = fields.Integer(string="Toggl ID", required=True, readonly=True)

    export_id = fields.Integer(string="Export ID", readonly=True)

    error = fields.Boolean(compute='_compute_error')

    task_id = fields.Many2one(
        comodel_name='toggl.task',
        compute='_compute_task_id',
        store=True,
        readonly=True,
    )

    invoicable = fields.Boolean(related='task_id.invoicable', store=True)

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

    def write(self, vals):
        res = super().write(vals)
        if 'name' in vals:
            children = self.mapped('child_ids')
            if children: # recursion condition
                children.write({'name': vals['name']})
        return res


    def export(self):
        url = self.env['ir.config_parameter'].sudo().get_param('toggl.export.url')
        dbname = self.env['ir.config_parameter'].sudo().get_param('toggl.export.dbname')
        username = self.env['ir.config_parameter'].sudo().get_param('toggl.export.username')
        pwd = self.env['ir.config_parameter'].sudo().get_param('toggl.export.pwd')

        if not all([url, dbname, username, pwd]):
            raise UserError(_("Export credentials not configured."))


        server_common = xmlrpc.client.ServerProxy(urllib.parse.urljoin(url, '/xmlrpc/common'))
        uid = server_common.authenticate(dbname, username, pwd, {})
        server_models = xmlrpc.client.ServerProxy(urllib.parse.urljoin(url, '/xmlrpc/object'))

        for record in self:
            export_id = record.export_id or record.parent_id.export_id
            if export_id:
                raise UserError(
                    _("%s has already been exported! (Export ID: %s)") % (record.display_name, record.export_id)
                )

            values = {
                'date': record.date,
                'name': ', '.join({e.description for e in (record | record.child_ids) if e.description} or '/'),
                'task_id': record.task_id.task_id,
                'project_id': record.task_id.project_id,
                'unit_amount': record.rounded_duration,
            }
            record.export_id = server_models.execute_kw(dbname, uid, pwd,
                'account.analytic.line', 'create',
                [
                    values,
                ],
            )
            record.env.cr.commit() # we need to commit, since the export is committed in the target system.


    @api.depends('invoicable', 'description')
    def _compute_error(self):
        for record in self:
            record.error = not record.description and record.invoicable


    @api.depends('total_duration')
    def _compute_rounded_duration(self):

        def roundto(x, base):
            return base * round(x/base)

        def ceilto(x, base):
            return base * math.ceil(x/base)

        for record in self:
            if record.invoicable:
                # Round up to half hour.
                record.rounded_duration = ceilto(record.total_duration, base=0.5)
            else:
                # Round to nearest 15min.
                record.rounded_duration = roundto(record.total_duration, base=0.25)


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
