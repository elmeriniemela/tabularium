# -*- coding: utf-8 -*-

import logging
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

class FightPlane(models.Model):
    _name = 'flight.plane'
    _description = 'Flight Plane'
    _inherit = ['mail.thread']

    name = fields.Char(required=True, tracking=True)
    company_id = fields.Many2one(comodel_name='res.company', tracking=True)

    @api.model
    def _name_search(self, name='', args=None, operator='ilike', limit=100, name_get_uid=None):
        resp = super()._name_search(name, args, operator, limit, name_get_uid)
        if not resp and self.env.context.get('import_file'):
            resp = super()._name_search(name, args, 'ilike', limit, name_get_uid)
        return resp
