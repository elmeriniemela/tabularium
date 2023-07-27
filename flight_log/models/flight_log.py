# -*- coding: utf-8 -*-

import datetime
import logging
from odoo import models, tools, fields, api, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

def ftime(time):
    return '{0:02.0f}:{1:02.0f}'.format(*divmod(time * 60, 60))

def ptime(time):
    try:
        h, m = time.split(':')
        h, m = float(h), float(m)
    except ValueError:
        raise ValidationError(_("Invalid time '%s', expected format '23:59'.") % time)
    m /= 60.0
    return h + m

class FightPlane(models.Model):
    _name = 'flight.plane'
    _description = 'Flight Plane'
    _inherit = ['mail.thread']

    name = fields.Char(required=True, tracking=True)


class FightAirport(models.Model):
    _name = 'flight.airport'
    _description = 'Flight Airport'
    _inherit = ['mail.thread']

    name = fields.Char(required=True, tracking=True)


class FlightLog(models.Model):
    _name = 'flight.log'
    _description = 'Flight Log'
    _order = 'date desc, start_time desc, id desc'
    _inherit = ['mail.thread']
    _check_company_auto = True


    name = fields.Char(
        required=True,
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
        copy=False,
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
        copy=False,
        default=0.0,
        states={'confirmed': [('readonly', True)]},
        group_operator=None,
    )

    end_time = fields.Float(
        tracking=True,
        required=True,
        copy=False,
        default=0.0,
        states={'confirmed': [('readonly', True)]},
        group_operator=None,
    )

    date = fields.Date(
        tracking=True,
        required=True,
        states={'confirmed': [('readonly', True)]},
        index=True,
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
        copy=False,
        states={'confirmed': [('readonly', True)]},
        default=0.0,
        required=True,
    )

    duration = fields.Float(
        compute='_compute_duration',
        store=True,
        copy=False,
    )

    search_date = fields.Char(compute='_compute_search_date', search='_search_date')
    search_start_time = fields.Char(compute='_compute_search_start_time', search='_search_start_time')
    search_end_time = fields.Char(compute='_compute_search_end_time', search='_search_end_time')

    def _search_date(self, operator, value):
        return [('date', 'like', value)]

    def _search_time(self, field, operator, value):
        if value.isdigit():
            hour = int(value)
            return [(field, '>=', hour), (field, '<=', hour+1)]
        return [(field, '=', ptime(value))]

    def _search_start_time(self, operator, value):
        return self._search_time('start_time', operator, value)

    def _search_end_time(self, operator, value):
        return self._search_time('end_time', operator, value)

    @api.constrains('start_time', 'end_time', 'date')
    def _constrain_time(self):
        for record in self:
            if record.end_time < record.start_time:
                raise ValidationError(_("End time can not be before start time"))

            if any(t < 0 or t > 24 for t in [record.end_time, record.start_time]):
                raise ValidationError(_("Time should be between 0h and 24h"))


            overlap = record.search([
                ('date', '=', record.date),
                ('id', '!=', record.id),
                ('start_time', '<=', record.end_time),
                ('end_time', '>=', record.start_time),
            ], limit=1)
            if overlap:
                raise ValidationError(_("There is already a flight on %s from %s to %s.") % (overlap.date, ftime(overlap.start_time), ftime(overlap.end_time)))



    @api.depends('start_time', 'end_time')
    def _compute_duration(self):
        for record in self:
            if record.start_time and record.end_time:
                record.duration = record.end_time - record.start_time
            else:
                record.duration = False

    def copy(self, default=None):
        default = dict(default or {})
        default.update(name=_("%s (copy)") % self.name)
        return super().copy(default)
