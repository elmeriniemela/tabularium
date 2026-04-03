# -*- coding: utf-8 -*-

import logging
from odoo import models, api, fields, exceptions, _

_logger = logging.getLogger(__name__)


class CloudModule(models.Model):
    _name = 'cloud.module'
    _description = 'Cloud Module'
    _inherit = ['mail.thread']
    _order = 'sequence, id desc'

    sequence = fields.Integer(
        string="Sequence",
        default=0,  # Set default=0 to avoid false values and messed up sequence order inside same parent
    )

    name = fields.Char(
        required=True,
        tracking=True,
    )

    _uniq_name = models.Constraint('UNIQUE(name)', 'Module name should be unique!')
