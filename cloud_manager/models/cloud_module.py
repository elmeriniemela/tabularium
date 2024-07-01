# -*- coding: utf-8 -*-

import logging
from odoo import models, api, fields, exceptions, _

_logger = logging.getLogger(__name__)


class CloudModule(models.Model):
    _name = 'cloud.module'
    _description = 'Cloud Module'
    _inherit = ['mail.thread']

    name = fields.Char(
        required=True,
        tracking=True,
    )

    _sql_constraints = [
        ('uniq_name', 'UNIQUE(name)', 'Module name should be unique!'),
    ]
