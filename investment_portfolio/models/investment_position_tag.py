# -*- coding: utf-8 -*-

from odoo import api, models, fields, _
import logging
import random

_logger = logging.getLogger(__name__)

class InvestmentPositionTag(models.Model):
    _name = 'investment.position.tag'
    _description = 'Position Tag'
    _order = "sequence, id"

    sequence = fields.Integer('Sequence', default=0)

    name = fields.Char(
        required=True,
    )

    color = fields.Integer(
        string='Color Index', default=lambda self: random.randint(1, 11),
    )

