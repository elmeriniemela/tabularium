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
    def _name_search(self, name, domain=None, operator='ilike', limit=None, order=None):
        resp = super()._name_search(name, domain=domain, operator=operator, limit=limit, order=order)
        if not resp and self.env.context.get('import_file'):
            resp = super()._name_search(name, domain=domain, operator='ilike', limit=limit, order=order)
        return resp


