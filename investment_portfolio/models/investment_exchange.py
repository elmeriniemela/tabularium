# -*- coding: utf-8 -*-

from odoo import api, models, fields, _
from odoo.addons.base.models.res_partner import _tz_get

import datetime
import pytz

class InvestmentExchange(models.Model):
    _name = 'investment.exchange'
    _description = 'Investment Exchange'
    _order = 'sequence, id'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(string='Sequence')

    opening_time = fields.Float(
        required=True,
        default=0.0,
        aggregator=None,
    )

    closing_time = fields.Float(
        required=True,
        default=0.0,
        aggregator=None,
    )

    next_close = fields.Datetime(compute='_compute_open_close')
    next_open = fields.Datetime(compute='_compute_open_close')
    is_open = fields.Boolean(compute='_compute_open_close')
    is_recently_open = fields.Boolean(compute='_compute_open_close')


    tz = fields.Selection(_tz_get, string="Timezone", default=lambda self: self.env.context.get('tz'))

    weekend_trading = fields.Boolean()

    gap_ids = fields.One2many(
        comodel_name='investment.exchange.gap',
        inverse_name='exchange_id',
    )


    @api.depends('tz', 'opening_time', 'closing_time', 'weekend_trading', 'gap_ids')
    def _compute_open_close(self):

        def localize(tz, date, float_time):
            second = microsecond = 0
            if float_time is not None:
                hour, minute = (int(t) for t in divmod(float_time * 60, 60))
                if minute == 59: # UI issue, causes the last minute to be left out. Decrease it to 1 microsecond.
                    second = 59
                    microsecond = 999999
            else: # pragma: no cover
                hour, minute = date.hour, date.minute

            return tz.localize(datetime.datetime(date.year, date.month, date.day, hour, minute, second, microsecond))

        def utclize(dt):
            return dt.astimezone(pytz.UTC).replace(tzinfo=None)

        for ex in self:
            tz = pytz.timezone(ex.tz)
            now_utc = fields.Datetime.now()
            now_local = pytz.UTC.localize(now_utc).astimezone(tz)
            schedule_now_local = now_local
            if not ex.weekend_trading:
                while schedule_now_local.isoweekday() in [6,7]:
                    schedule_now_local += datetime.timedelta(days=1)

            next_close = localize(tz, schedule_now_local, ex.closing_time)
            while next_close <= schedule_now_local:
                new = localize(tz, next_close + datetime.timedelta(days=1), ex.closing_time)
                assert new > next_close
                next_close = new


            next_open = localize(tz, next_close, ex.opening_time)

            gaps = ex.gap_ids.filtered(lambda g: g.date == next_open.date())
            while any(g.closing_datetime.astimezone(tz) <= next_open for g in gaps):
                next_open += datetime.timedelta(days=1)
                gaps = ex.gap_ids.filtered(lambda g: g.date == next_open.date())

            ex.next_open = utclize(next_open)
            closing_times = [ex.closing_time] + [g.closing_time for g in gaps if g.closing_time]
            ex.next_close = utclize(localize(tz, next_open, min(closing_times)))

            ex.is_open = (ex.next_open <= now_utc and ex.next_close >= now_utc)
            recent_close_local = localize(tz, now_local, ex.closing_time)
            if recent_close_local > now_local:
                recent_close_local -= datetime.timedelta(days=1)
            while not ex.weekend_trading and recent_close_local.isoweekday() in [6,7]:
                recent_close_local -= datetime.timedelta(days=1)

            seconds_since_close = (now_utc - utclize(recent_close_local)).total_seconds()
            ex.is_recently_open = ex.is_open or 0 <= seconds_since_close <= 30 * 60


