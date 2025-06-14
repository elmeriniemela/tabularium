# -*- coding: utf-8 -*-

from odoo import api, models, fields, _
import logging
import datetime
import pytz

_logger = logging.getLogger(__name__)

class InvestmentExchangeGap(models.Model):
    _name = 'investment.exchange.gap'
    _description = 'Exchange Gap'
    _order = "sequence, id desc"

    exchange_id = fields.Many2one(
        comodel_name='investment.exchange',
        required=True,
        ondelete='cascade',
        index=True,
    )

    date = fields.Date(
        required=True,
    )

    closing_time = fields.Float(
        default=0.0,
        aggregator=None,
    )

    closing_datetime = fields.Datetime(compute='_compute_closing_datetime')

    sequence = fields.Integer('Sequence', default=0)

    name = fields.Char(
        required=True,
    )

    @api.depends('exchange_id.tz', 'closing_time', 'date')
    def _compute_closing_datetime(self):
        for gap in self:
            if gap.closing_time:
                hour, minute = (int(t) for t in divmod(gap.closing_time * 60, 60))
            else:
                hour = minute = 0

            tz = pytz.timezone(gap.exchange_id.tz)
            date = gap.date
            if date:
                gap.closing_datetime = tz.localize(datetime.datetime(date.year, date.month, date.day, hour, minute, 0, 0)).astimezone(pytz.UTC).replace(tzinfo=None)
            else:
                gap.closing_datetime = False

