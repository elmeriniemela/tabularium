# -*- coding: utf-8 -*-

import logging
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

class FlightLog(models.Model):
    _name = 'flight.log'
    _description = 'Flight Log'
    _order = 'date desc, start_time desc, id desc'
    _inherit = ['mail.thread']
    _check_company_auto = True

    company_id = fields.Many2one(
        comodel_name='res.company',
        required=True,
        default=lambda self: self.env.company,
        tracking=True,
        states={'confirmed': [('readonly', True)]},
    )

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

    import_start_time = fields.Char(compute='_compute_import_time', inverse='_inverse_import_time', readonly=False)
    import_end_time = fields.Char(compute='_compute_import_time', inverse='_inverse_import_time', readonly=False)

    date = fields.Date(
        tracking=True,
        required=True,
        states={'confirmed': [('readonly', True)]},
        index=True,
    )

    purpose = fields.Selection(
        string="Purpose (deprecated)",
        selection=[
            ('KOU', 'Koulutus'),
            ('OPE', 'Opetus'),
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

    purpose_id = fields.Many2one(
        comodel_name='flight.purpose',
        required=True,
        index=True,
        tracking=True,
        states={'confirmed': [('readonly', True)]},
        ondelete='restrict',
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

    signatory_license_number = fields.Char(
        string="Signatory's license number",
        states={'confirmed': [('readonly', True)]},
        tracking=True,
        copy=False,
    )

    sign = fields.Binary(
        states={'confirmed': [('readonly', True)]},
        tracking=True,
        copy=False,
    )

    skip_validation = fields.Boolean(
        tracking=True,
        copy=False,
    )

    search_date = fields.Char(compute='_compute_search_date', search='_search_date')
    search_start_time = fields.Char(compute='_compute_search_start_time', search='_search_start_time')
    search_end_time = fields.Char(compute='_compute_search_end_time', search='_search_end_time')

    @staticmethod
    def ftime(time):
        return '{0:02.0f}:{1:02.0f}'.format(*divmod(time * 60, 60))

    @staticmethod
    def ptime(time):
        try:
            h, m = time.split(':')
            h, m = float(h), float(m)
        except ValueError:
            raise ValidationError(_("Invalid time '%s', expected format '23:59'.") % time)
        m /= 60.0
        return h + m

    def _search_date(self, operator, value):
        return [('date', 'like', value)]

    def _search_time(self, field, operator, value):
        if value.isdigit():
            hour = int(value)
            return [(field, '>=', hour), (field, '<=', hour+1)]
        return [(field, '=', self.ptime(value))]

    def _search_start_time(self, operator, value):
        return self._search_time('start_time', operator, value)

    def _search_end_time(self, operator, value):
        return self._search_time('end_time', operator, value)

    @api.constrains('start_time', 'end_time', 'date', 'skip_validation')
    def _constrain_time(self):
        for record in self:
            if record.skip_validation:
                continue
            if record.end_time < record.start_time:
                raise ValidationError(_("End time (%s) can not be before start time (%s)") % (record.ftime(record.end_time), record.ftime(record.start_time)))

            if any(t < 0 or t > 24 for t in [record.end_time, record.start_time]):
                raise ValidationError(_("Time should be between 0h and 24h"))


            overlap = record.search([
                ('company_id', '=', record.company_id.id),
                ('date', '=', record.date),
                ('id', '!=', record.id),
                ('start_time', '<=', record.end_time),
                ('end_time', '>=', record.start_time),
            ], limit=1)
            if overlap:
                raise ValidationError(_("Unable to add flight on %s from %s to %s as there is already a flight on %s from %s to %s.") % (
                    record.date, record.ftime(record.start_time), record.ftime(record.end_time),
                    overlap.date, overlap.ftime(overlap.start_time), overlap.ftime(overlap.end_time)))


    def _compute_import_time(self):
        for record in self:
            record.import_end_time = record.ftime(record.end_time)
            record.import_start_time = record.ftime(record.start_time)

    def _inverse_import_time(self):
        for record in self:
            record.write({
                'end_time': record.ptime(record.import_end_time) if record.import_end_time else False,
                'start_time': record.ptime(record.import_start_time) if record.import_start_time else False,
            })


    @api.depends('start_time', 'end_time')
    def _compute_duration(self):
        for record in self:
            if isinstance(record.start_time, float) and isinstance(record.end_time, float):
                record.duration = record.end_time - record.start_time
            else:
                record.duration = False

    def copy(self, default=None):
        default = dict(default or {})
        default.update(name=_("%s (copy)") % self.name)
        return super().copy(default)
