# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class AccountCostTag(models.Model):
    _name = 'account.cost.tag'
    _description = 'Account Cost Tag'

    name = fields.Char(required=True)
    color = fields.Integer('Color Index')



class AccountMove(models.Model):
    _inherit = 'account.move'

    cost_tag_ids = fields.Many2many('account.cost.tag', string='Cost')

    cost_date_start = fields.Date("From")
    cost_date_end = fields.Date("To")
    cost_warning = fields.Text(compute='_compute_cost_warning')

    @api.depends('cost_tag_ids', 'cost_date_start', 'cost_date_end')
    def _compute_cost_warning(self):
        for record in self:
            record.cost_warning = False
            if not record.cost_tag_ids or record.state == 'cancel':
                continue
            domain = [
                '!', # not
                '|', # or
                # Earliest date can't be after date_to (period end)
                ('cost_date_start', '>', record.cost_date_end),
                # Latest date can't be before date_from (period start)
                ('cost_date_end', '<', record.cost_date_start),
                ('cost_tag_ids', 'in', record.cost_tag_ids.ids)
            ]

            overlapping = record.search(domain) - record
            if overlapping:
                record.cost_warning = _("Same cost range with following invoices:\n%s") % '\n'.join(overlapping.mapped('display_name'))

    @api.constrains('cost_date_start', 'cost_date_end')
    def _constrains_cost_date(self):
        for record in self:
            if (record.cost_date_start and record.cost_date_end) and record.cost_date_start > record.cost_date_end:
                raise ValidationError(
                    _("Cost start date can't be after cost end date.")
                )



