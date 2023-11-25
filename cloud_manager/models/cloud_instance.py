# -*- coding: utf-8 -*-

import logging
from odoo import models, api, fields, _

_logger = logging.getLogger(__name__)


class CloudInstance(models.Model):
    _name = 'cloud.instance'
    _description = 'Cloud Instance'
    _inherit = ['mail.thread']

    name = fields.Char(
        required=True,
        tracking=True,
    )

    endpoint_id = fields.Many2one(
        comodel_name='api.endpoint',
        required=True,
        ondelete='restrict'
    )

