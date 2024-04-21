# -*- coding: utf-8 -*-

from odoo import models, fields, _


class InvestmentCategory(models.Model):
    _name = 'investment.category'
    _description = 'Investment Category'
    _order = 'sequence, id'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(string='Sequence')
    liquid = fields.Boolean()
