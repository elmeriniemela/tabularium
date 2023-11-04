# -*- coding: utf-8 -*-

import logging
from odoo import models, tools, fields, api, _

_logger = logging.getLogger(__name__)


class ApiMessage(models.Model):
    _name = 'api.message'
    _description = 'API Message'
    _inherit = ['mail.thread']


    name = fields.Char(required=True, readonly=True)
    state = fields.Selection(
        selection=[
            ('waiting', 'Waiting'),
            ('done', 'Done'),
        ],
        required=True,
        tracking=True,
        default='waiting',
    )

    content = fields.Binary(required=True)

    endpoint_id = fields.Many2one(
        comodel_name='api.endpoint',
        required=True,
        ondelete='cascade',
    )

