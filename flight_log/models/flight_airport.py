# -*- coding: utf-8 -*-

import logging
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class FightAirport(models.Model):
    _name = 'flight.airport'
    _description = 'Flight Airport'
    _inherit = ['mail.thread']
    _order = 'sequence, id'

    name = fields.Char(required=True, tracking=True)
    company_id = fields.Many2one(comodel_name='res.company', tracking=True)
    sequence = fields.Integer()

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        resp = super().name_search(name=name, args=args, operator=operator, limit=limit)
        if not resp and self.env.context.get('import_file'):
            resp = super().name_search(name=name, args=args, operator='ilike', limit=limit)
        return resp


