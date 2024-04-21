# -*- coding: utf-8 -*-

from odoo import models, fields, _


class InvestmentPortfolio(models.Model):
    _name = 'investment.portfolio'
    _description = 'Investment Portfolio'
    _order = 'sequence, id'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(string='Sequence')
