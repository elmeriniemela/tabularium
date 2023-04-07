# -*- coding: utf-8 -*-

from odoo import models, tools, fields, api, _
import re
from odoo.exceptions import UserError
import logging
from odoo.tools import float_is_zero, float_compare

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

    sale_line_name = fields.Char(readonly=True)
    sale_line_id = fields.Integer(readonly=True)

    company_id = fields.Many2one(comodel_name='res.company', required=True, default=lambda self: self.env.company, tracking=True)

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
            {'fields': ['sale_line_id', 'project_id', 'id', 'display_name']}
        )

        project_map = {d['id']: d['project_id'] for d in task_res if d['project_id']}
        sale_line_map = {d['id']: d['sale_line_id'] for d in task_res if d['sale_line_id']}
        name_map = {d['id']: d['display_name'] for d in task_res if d['display_name']}

        for record in self:
            record.project_id, record.project_name = project_map.get(record.task_id, (False, False))
            record.sale_line_id, record.sale_line_name = sale_line_map.get(record.task_id, (False, False))
            record.name = name_map.get(record.task_id, record.name)


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
    _order = 'date desc, id asc'
    _inherit = ['mail.thread']
    _check_company_auto = True

    name = fields.Char(required=True, readonly=True)

    export_task_url = fields.Char(compute='_compute_export_task_url')

    active = fields.Boolean(default=True, tracking=True)

    description = fields.Char(tracking=True)

    rounded_duration = fields.Float(compute='_compute_toggl_fields', store=True)

    date = fields.Date(compute='_compute_toggl_fields', store=True)

    total_duration = fields.Float(compute='_compute_toggl_fields', store=True, recursive=True)

    extra_duration = fields.Float(tracking=True)
    duration = fields.Float(required=True, readonly=True)

    original_price = fields.Monetary(currency_field='company_currency_id', group_operator="avg")
    timesheet_price = fields.Monetary(currency_field='company_currency_id', group_operator="avg")
    revenue = fields.Monetary(
        compute='_compute_revenue',
        store=True,
        currency_field='company_currency_id')
    price_initialized = fields.Boolean()
    company_id = fields.Many2one(comodel_name='res.company', required=True, default=lambda self: self.env.company, tracking=True)
    company_currency_id = fields.Many2one(related='company_id.currency_id', string="Company Currency")

    start = fields.Datetime(required=True, readonly=True)

    stop = fields.Datetime(required=True, readonly=True)

    toggl_id = BigInteger(string="Toggl ID", required=True, readonly=True)

    export_id = fields.Integer(
        string="Export ID", readonly=True,
        inverse='_inverse_export_id',
    )

    task_id = fields.Many2one(
        comodel_name='toggl.task',
        compute='_compute_toggl_fields',
        store=True,
        readonly=True,
        check_company=True,
    )

    project_name = fields.Char(related='task_id.project_name')

    parent_id = fields.Many2one(
        comodel_name='toggl.entry',
        compute='_compute_toggl_fields',
        store=True,
        readonly=True,
        check_company=True,
        ondelete='cascade',
    )

    child_ids = fields.One2many(
        comodel_name='toggl.entry',
        inverse_name='parent_id',
        readonly=True,
    )

    locked = fields.Datetime()

    price_changed = fields.Boolean()

    time_period = fields.Char(compute='_compute_time_period')

    @property
    def timesheet_rounding(self):
        return 15/60

    @property
    def task_id_regex(self):
        return '\[(\d+)\]'

    _sql_constraints = [
        ('export_id_uniq', 'unique(export_id)', 'The export_id must be unique!'),
        ('export_id_non_zero', 'CHECK(export_id <> 0)', 'The export_id can not be zero!'),
        ('toggl_id_uniq', 'unique(toggl_id)', 'The toggl_id must be unique!'),
    ]

    def _inverse_export_id(self):
        for record in self:
            export_id = record.export_id or False
            if export_id and record.parent_id and not record.parent_id.export_id:
                # Move to parent
                (record | record.parent_id).flush()
                record.env.cr.execute(f"UPDATE {record._table} SET export_id=NULL WHERE id={record.id}")
                record.env.cr.execute(f"UPDATE {record._table} SET export_id={export_id} WHERE id={record.parent_id.id}")

    @api.depends('task_id.task_id')
    def _compute_export_task_url(self):
        url = self.env.user.toggl_export_url
        for record in self:
            record.export_task_url = '%sweb#id=%d&view_type=form&model=project.task' % (url, record.task_id.task_id or 0)

    def _compute_time_period(self):
        time_str = lambda dt: fields.Datetime.context_timestamp(self, dt).strftime('%H:%M:%S')
        for record in self:
            record.time_period = f"{time_str(record.start)} - {time_str(record.stop)}"

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
        self.extra_duration += self.timesheet_rounding

    def action_reset_rounding(self):
        self.ensure_one()
        self.extra_duration = 0

    def action_round_down(self):
        self.ensure_one()
        self.extra_duration -= self.timesheet_rounding

    def export(self):
        no_task = self.filtered(lambda e: not e.task_id)
        if no_task:
            raise UserError(_("Unable to export %s. Task ID missing.") %  no_task.mapped('name'))
        self.mapped('task_id').fetch()

        server_models, dbname, uid, pwd = self.env.user._get_toggl_export_proxy()

        for record in self:
            values = {
                'date': record.date,
                'name': record.description,
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
        self.update_timesheet_price()
        self.lock()


    def update_timesheet_price(self):
        server_models, dbname, uid, pwd = self.env.user._get_toggl_export_proxy()

        timesheet_res = server_models.execute_kw(dbname, uid, pwd,
            'account.analytic.line', 'search_read',
            [[
                ['id', 'in', self.mapped('export_id')],
            ]],
            {'fields': ['invoice_estimate_unit_price', 'id']}
        )
        price_unit_map = {d['id']: d['invoice_estimate_unit_price'] for d in timesheet_res}

        for record in self:
            price = price_unit_map.get(record.export_id) or 0.0
            record.timesheet_price = price
            if not record.price_initialized:
                record.original_price = price
                record.price_initialized = True
            record.price_changed = not float_is_zero(record.original_price - record.timesheet_price, precision_digits=2)



    def recompute_depends(self):
        self._compute_toggl_fields()
        (self | self.child_ids).filtered(lambda e: e.export_id)._inverse_export_id()

    def lock(self):
        for record in self:
            (record | record.child_ids).locked = fields.Datetime.now()

    def unlock(self):
        for record in self:
            (record | record.child_ids).locked = False


    @api.depends('name', 'start', 'duration', 'duration', 'extra_duration')
    def _compute_toggl_fields(self):
        Task = self.env['toggl.task']
        daily_entries = (self._origin | self.search([('date', 'in', [False]+self.mapped('date'))])).sorted('id')
        daily_entries = daily_entries.filtered(lambda e: not e.locked)


        for record in daily_entries:
            ids = [int(m) for m in re.findall(record.task_id_regex, record.name or '')]
            if ids:
                [task_id] = ids
                record.task_id = Task.search([('task_id', '=', task_id),('company_id', '=', record.company_id.id)], limit=1) \
                    or Task.create({
                        'name': record.name,
                        'task_id': task_id
                    })
            else:
                record.task_id = False

            record.date = record.start.date()


        for key, same_tasks in tools.groupby(daily_entries, lambda e: (e['name'], e['date'])):
            parent = same_tasks[0]
            parent.parent_id = False

            total_duration = parent.duration
            extra_duration = parent.extra_duration
            for child in same_tasks[1:]:
                child.parent_id = parent
                child.total_duration = child.duration
                child.rounded_duration = roundto(child.duration or 0.0, base=self.timesheet_rounding)
                total_duration += child.duration
                extra_duration += child.extra_duration

            parent.total_duration = total_duration
            parent.rounded_duration = roundto(parent.total_duration + extra_duration or 0.0, base=self.timesheet_rounding)

    @api.depends('rounded_duration', 'timesheet_price')
    def _compute_revenue(self):
        for record in self:
            record.revenue = record.rounded_duration * record.timesheet_price

