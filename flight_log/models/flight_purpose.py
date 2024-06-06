# -*- coding: utf-8 -*-

import logging
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class FightPurpose(models.Model):
    _name = 'flight.purpose'
    _description = 'Flight Purpose'
    _inherit = ['mail.thread']
    _order = 'sequence, id'

    name = fields.Char(required=True, tracking=True, translate=True)

    code = fields.Char(required=True, tracking=True)

    sequence = fields.Integer()


    @api.model
    def _name_search(self, name='', args=None, operator='ilike', limit=100, name_get_uid=None):
        resp = super()._name_search(name, args, operator, limit, name_get_uid)
        if not resp and self.env.context.get('import_file'):
            resp = super()._name_search(name, args, 'ilike', limit, name_get_uid)
        return resp

