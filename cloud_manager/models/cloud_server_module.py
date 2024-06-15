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

    server_id = fields.Many2one(
        string="Server",
        comodel_name='cloud.server',
        required=True,
        index=True,
        ondelete='cascade',
    )


    name = fields.Char(
        required=True,
        tracking=True,
    )

    directory = fields.Char(
        required=True,
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

    def action_update_server(self):
        pass

