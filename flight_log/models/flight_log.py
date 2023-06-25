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
    _order = 'start asc, id desc'
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

    start = fields.Datetime(
        tracking=True,
        required=True,
        states={'confirmed': [('readonly', True)]},
    )
    end = fields.Datetime(
        tracking=True,
        required=True,
        states={'confirmed': [('readonly', True)]},
    )

    start_time = fields.Float(
        compute='_compute_time',
        store=True,
    )

    end_time = fields.Float(
        compute='_compute_time',
        store=True,
    )

    date = fields.Date(
        compute='_compute_date',
        store=True,
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

    @api.depends('start', 'end', 'date')
    def _compute_time(self):
        for record in self:
            record.start_time = ((record.start-record.start.replace(hour=0, minute=0, second=0, microsecond=0) + datetime.timedelta(hours=3)).seconds/(60*60))
            record.end_time = ((record.end-record.end.replace(hour=0, minute=0, second=0, microsecond=0) + datetime.timedelta(hours=3)).seconds/(60*60))

    @api.depends('start_time', 'end_time')
    def _compute_duration(self):
        for record in self:
            if record.start_time and record.end_time:
                record.duration = record.end_time - record.start_time
            else:
                record.duration = False


    @api.depends('start')
    def _compute_date(self):
        for record in self:
            if record.start:
                record.date = record.start.date()
            else:
                record.date = False
