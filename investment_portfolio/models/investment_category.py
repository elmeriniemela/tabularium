# -*- coding: utf-8 -*-

from odoo import models, fields, _


class InvestmentCategory(models.Model):
    _name = 'investment.category'
    _description = 'Investment Category'
    _order = 'sequence, id'


    name = fields.Char(required=True)
    sequence = fields.Integer(string='Sequence')
    liquid = fields.Boolean()
    parent_id = fields.Many2one(
        comodel_name='investment.category',
        compute='_compute_parent_id',
        store=True,
        readonly=False,
    )

    def _compute_parent_id(self):
        for record in self:
            record.parent_id = record.parent_id or record
