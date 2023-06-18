# -*- coding: utf-8 -*-

from odoo import api, models, fields, _
from dateutil.relativedelta import relativedelta

from odoo.tools.safe_eval import safe_eval


class InvestmentMilestone(models.Model):
    _name = 'investment.milestone'
    _inherit = ['mail.thread']
    _description = 'Investment Milestone'
    _order = 'date asc'

    name = fields.Char(required=True)

    date = fields.Date(required=True, tracking=True)

    domain = fields.Text(default="[('liquid', '=', True)]", required=True, tracking=True)

    position = fields.Monetary(string="Target Position", required=True, currency_field='company_currency_id', tracking=True)

    inflation_rate = fields.Float(default=0.07, tracking=True)

    real_position = fields.Monetary(compute='_compute_real_position', currency_field='company_currency_id')

    company_id = fields.Many2one(
        comodel_name='res.company',
        required=True,
        default=lambda self: self.env.company,
        tracking=True,
        index=True,
    )

    company_currency_id = fields.Many2one(related='company_id.currency_id', string="Company Currency")

    state = fields.Selection(
        selection=[
            ('ahead', 'Ahead'),
            ('behind', 'Behind'),
            ('missed', 'Missed'),
            ('reached', 'Reached'),
        ],
        compute='_compute_state',
    )

    predicted_position = fields.Monetary(
        string="Predicted/Actual Position",
        compute='_compute_state',
        currency_field='company_currency_id',
    )

    difference = fields.Monetary(
        compute='_compute_state',
        currency_field='company_currency_id',
    )

    timeseries_ids = fields.Many2many(
        comodel_name='investment.timeseries',
        compute='_compute_state',
    )

    def copy(self, default=None):
        default = default or {
            'date': self.date+relativedelta(years=1),
            'name': self.name + ' (copy)',
        }
        return super().copy(default)

    def copy_button(self):
        self.ensure_one()
        self.copy()

    @api.depends('position', 'date')
    def _compute_state(self):
        today = fields.Date.today()
        for record in self:
            domain = safe_eval(record.domain)
            record.timeseries_ids = record.env['investment.timeseries'].search(domain+[('date', '=', record.date)])
            record.predicted_position = sum(record.timeseries_ids.mapped('position'))
            record.difference = record.predicted_position - record.position
            if record.difference < 0:
                record.state = 'behind' if (record.date or today) > today else 'missed'
            else:
                record.state = 'ahead' if (record.date or today) > today else 'reached'


    @api.depends('position', 'inflation_rate', 'date')
    def _compute_real_position(self):
        reference = self.search([], limit=1)
        for record in self:
            if record.date:
                record.real_position = record.position * (1 - record.inflation_rate)**((record.date-reference.date).days/365)
            else:
                record.real_position = record.position
