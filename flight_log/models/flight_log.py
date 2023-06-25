# -*- coding: utf-8 -*-

import datetime
import logging
from odoo import models, tools, fields, api, _

_logger = logging.getLogger(__name__)

class FightPlane(models.Model):
    _name = 'flight.plane'
    _description = 'Flight Plane'
    _inherit = ['mail.thread']

    name = fields.Char(required=True, tracking=True)


class FightPlane(models.Model):
    _name = 'flight.airport'
    _description = 'Flight Plane'
    _inherit = ['mail.thread']

    name = fields.Char(required=True, tracking=True)


class FlightLog(models.Model):
    _name = 'flight.log'
    _description = 'Flight Log'
    _order = 'date asc, start_time asc, id asc'
    _inherit = ['mail.thread']
    _check_company_auto = True


    name = fields.Char(
        required=True,
        default='HAR',
        tracking=True,
        states={'confirmed': [('readonly', True)]},
    )
    desc = fields.Char(
        tracking=True,
        states={'confirmed': [('readonly', True)]},
    )

    airport_takeoff_id = fields.Many2one(
        comodel_name='flight.airport',
        required=True,
        index=True,
        states={'confirmed': [('readonly', True)]},
        ondelete='restrict',
        tracking=True,
    )
    airport_landing_id = fields.Many2one(
        comodel_name='flight.airport',
        required=True,
        index=True,
        states={'confirmed': [('readonly', True)]},
        ondelete='restrict',
        tracking=True,
    )

    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('confirmed', 'Confirmed'),
        ],
        required=True,
        default='draft',
        tracking=True,
    )

    plane_id = fields.Many2one(
        comodel_name='flight.plane',
        required=True,
        index=True,
        tracking=True,
        states={'confirmed': [('readonly', True)]},
        ondelete='restrict',
    )

    start_time = fields.Float(
        tracking=True,
        required=True,
        states={'confirmed': [('readonly', True)]},
        group_operator=None,
    )

    end_time = fields.Float(
        tracking=True,
        required=True,
        states={'confirmed': [('readonly', True)]},
        group_operator=None,
    )

    date = fields.Date(
        tracking=True,
        required=True,
        states={'confirmed': [('readonly', True)]},
    )

    purpose = fields.Selection(
        selection=[
            ('KOU', 'Koulutus'),
            ('HAR', 'Harjoitus'),
            ('LEN', 'Lennätys'),
            ('TAR', 'Tarkastuslento'),
            ('TYY', 'Tyyppilento'),
        ],
        states={'confirmed': [('readonly', True)]},
        default='HAR',
        required=True,
        tracking=True,
    )

    departure_method = fields.Selection(
        selection=[
            ('V', 'Vintturi'),
            ('L', 'Lentokone hinaus'),
        ],
        states={'confirmed': [('readonly', True)]},
        required=True,
        tracking=True,
        default='V',
    )

    instrumental_time = fields.Float(
        tracking=True,
        states={'confirmed': [('readonly', True)]},
    )

    duration = fields.Float(
        compute='_compute_duration',
        store=True,
    )

    @api.depends('start_time', 'end_time')
    def _compute_duration(self):
        for record in self:
            if record.start_time and record.end_time:
                record.duration = record.end_time - record.start_time
            else:
                record.duration = False

