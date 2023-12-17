# -*- coding: utf-8 -*-

import logging
from odoo import models, api, fields, exceptions, _

_logger = logging.getLogger(__name__)


class CloudRestore(models.TransientModel):
    _name = 'cloud.restore'
    _description = 'Cloud Restore'

    instance_id = fields.Many2one(
        comodel_name='cloud.instance',
        required=True,
        ondelete='cascade',
        domain=[('state', '=', 'exited')],
    )

    backup_id = fields.Many2one(
        comodel_name='cloud.backup',
        required=True,
        ondelete='cascade',
    )

    def action_restore(self):
        return self.backup_id._restore(self.instance_id)

