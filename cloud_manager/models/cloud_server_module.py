# -*- coding: utf-8 -*-

import logging
from odoo import models, api, fields, exceptions, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class CloudServerModule(models.Model):
    _name = 'cloud.server.module'
    _description = 'Cloud Server Module'
    _inherit = ['mail.thread']
    _order = 'id desc'

    active = fields.Boolean(
        tracking=True,
        default=True,
    )

    server_id = fields.Many2one(
        string="Server",
        comodel_name='cloud.server',
        required=True,
        index=True,
        ondelete='cascade',
        tracking=True,
    )

    name = fields.Char(related='module_id.name')

    module_id = fields.Many2one(
        string="Module",
        comodel_name='cloud.module',
        required=True,
        index=True,
        ondelete='restrict',
        tracking=True,
    )

    url = fields.Char(
        required=True,
        tracking=True,
    )

    branch = fields.Char(
        required=True,
        tracking=True,
    )

    commit = fields.Char(
        required=True,
        tracking=True,
    )

    diff_ids = fields.One2many(
        comodel_name='cloud.server.diff',
        inverse_name='module_id',
    )


    _sql_constraints = [
        ('uniq_mod', 'UNIQUE(server_id, module_id)', 'The server already has this module!'),
    ]

