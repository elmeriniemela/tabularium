# -*- coding: utf-8 -*-

from odoo import models, tools, fields, api, _
import re
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

def roundto(x, base):
    return base * round(x/base)

class TogglTask(models.Model):
    _name = 'toggl.task'
    _description = 'Toggl Task'
    _order = 'task_id desc'

    name = fields.Char(required=True, readonly=True)

    task_id = fields.Integer(required=True, readonly=True)

    project_name = fields.Char(readonly=True)
    project_id = fields.Integer(readonly=True)

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
        server_models, dbname, uid, pwd = self.env.user._get_toggl_export_proxy()
        task_res = server_models.execute_kw(dbname, uid, pwd,
            'project.task', 'search_read',
            [[
                ['id', 'in', self.mapped('task_id')],
                ['active', 'in', [True, False]],
            ]],
            {'fields': ['sale_line_id', 'project_id', 'id']}
        )

        project_map = {d['id']: d['project_id'] for d in task_res if d['project_id']}
        sale_line_map = {d['id']: d['sale_line_id'][0] for d in task_res if d['sale_line_id']}

        sale_line_res = server_models.execute_kw(dbname, uid, pwd,
            'sale.order.line', 'search_read',
            [[
                ['id', 'in', list(sale_line_map.values())]
            ]],
            {'fields': ['price_unit', 'id']}
        )

        price_unit_map = {d['id']: d['price_unit'] for d in sale_line_res}


        for record in self:
            record.project_id, record.project_name = project_map.get(record.task_id, (False, False))
            if price_unit_map.get(sale_line_map.get(record.task_id), 0.0) > 0.0:
                record.invoicable = True
            else:
                record.invoicable = False


    def write(self, vals):
        "TODO: for some reason the depends does not work."
        res = super().write(vals)
        if 'invoicable' in vals:
            self.mapped('entry_ids').recompute_depends()
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

class BigInteger(fields.Integer):
    column_type = ('int8', 'int8')

class TogglEntry(models.Model):
    _name = 'toggl.entry'
    _description = 'Toggl Entry'
    _order = 'start desc'
    _inherit = ['mail.thread']

    name = fields.Char(required=True)

    export_task_url = fields.Char(compute='_compute_export_task_url')

    active = fields.Boolean(default=True, tracking=True)

    toggl_name = fields.Char(required=True)

    description = fields.Char(tracking=True)

    rounded_duration = fields.Float(compute='_compute_rounded_duration', store=True)

    dirty = fields.Boolean(compute='_compute_dirty')

    date = fields.Date(compute='_compute_date', store=True)

    total_duration = fields.Float(compute='_compute_total_duration', store=True, recursive=True)

    extra_duration = fields.Float(tracking=True)
    duration = fields.Float(required=True, readonly=True)

    start = fields.Datetime(required=True, readonly=True)

    stop = fields.Datetime(required=True, readonly=True)

    toggl_id = BigInteger(string="Toggl ID", required=True, readonly=True)

    export_id = fields.Integer(
        string="Export ID", readonly=True,
    )

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

    # def _inverse_export_id(self):
    #     for record in self:
    #         export_id = record.export_id
    #         if export_id and record.parent_id and not record.parent_id.export_id:
    #             # Move to parent
    #             record.export_id = False
    #             record.parent_id.export_id = export_id

    @api.depends('task_id.task_id')
    def _compute_export_task_url(self):
        url = self.env.user.toggl_export_url
        for record in self:
            record.export_task_url = '%sweb#id=%d&view_type=form&model=project.task' % (url, record.task_id.task_id or 0)


    def write(self, vals):
        res = super().write(vals)
        if 'name' in vals:
            children = self.mapped('child_ids')
            if children: # recursion condition
                children.write({'name': vals['name']})
        return res

    def action_open_form(self):
        self.ensure_one()
        [action] = self.env.ref('toggl_sync.entry_action').read()
        action.update({
            'views': [[False, 'form']],
            'res_id': self.id
        })
        return action

    def action_view_task(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': self.export_task_url,
        }

    def action_round_up(self):
        self.ensure_one()
        self.extra_duration = 7.5/60

    def action_round_down(self):
        self.ensure_one()
        self.extra_duration = -7.5/60

    def export(self):
        self.mapped('task_id').fetch()

        server_models, dbname, uid, pwd = self.env.user._get_toggl_export_proxy()

        for record in self:
            values = {
                'date': record.date,
                'name': ', '.join({e.description for e in (record | record.child_ids) if e.description and e.description != e.name} or '/'),
                'task_id': record.task_id.task_id,
                'project_id': record.task_id.project_id,
                'unit_amount': record.rounded_duration,
            }
            export_id = record.export_id or record.parent_id.export_id
            if export_id:
                method_args = 'account.analytic.line', 'write', [export_id, values]
            else:
                method_args = 'account.analytic.line', 'create', [values]

            result = server_models.execute_kw(dbname, uid, pwd, *method_args)
            if not export_id:
                record.export_id = result
            record.env.cr.commit() # we need to commit, since the export is committed in the target system.


    @api.depends('total_duration', 'extra_duration')
    def _compute_rounded_duration(self):
        for record in self:
            # Round to nearest 15min.
            record.rounded_duration = roundto(record.total_duration + record.extra_duration or 0.0, base=0.25)


    @api.depends('duration', 'child_ids.duration', 'child_ids.total_duration')
    def _compute_total_duration(self):
        for record in self:
            record.total_duration = record.duration + sum(record.child_ids.mapped('total_duration'))


    def recompute_depends(self):
        self._compute_task_id()
        self._compute_date()
        self._compute_parent_id() # needs task_id, date,
        self._compute_total_duration() # needs parent_id
        self._compute_rounded_duration() # needs total_duration
        self._compute_dirty()
        # (self | self.child_ids).filtered(lambda e: e.export_id)._inverse_export_id()


    @api.depends('name')
    def _compute_task_id(self):
        Task = self.env['toggl.task']
        for record in self:
            ids = [int(m) for m in re.findall('\[(\d+)\]', record.name or '')]
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
        records_and_children = self | self.search([('date', 'in', self.mapped('date'))])
        for key, same_tasks in tools.groupby(records_and_children, lambda e: (e['task_id'] or e['name'], e['date'])):
            parent = same_tasks[0]
            for entry in same_tasks[1:]:
                entry.parent_id = parent


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
            record.env.user.toggl_update_time_entry(
                time_entry_id=record.toggl_id,
                json={'time_entry': {'description': record.name}}
            )
            record.toggl_name = record.name
