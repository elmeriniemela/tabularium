# -*- coding: utf-8 -*-

import logging
import dateutil
import pytz
import datetime
from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class TogglImport(models.TransientModel):
    _name = 'toggl.import'
    _description = 'Toggl Import'

    start_date = fields.Datetime(
        required=True,
        default=lambda self: self.env['toggl.entry'].search([], limit=1).stop - datetime.timedelta(days=1)
    )

    end_date = fields.Datetime(
        required=True,
        default=lambda self: fields.Datetime.now() + datetime.timedelta(days=1)
    )

    def import_entries(self):
        entries = self.env.user.toggl_time_entries(self.start_date, self.end_date)
        entries.mapped('task_id').fetch()

        date = lambda dt_str: dateutil.parser.parse(dt_str).astimezone(pytz.utc).replace(tzinfo=None)

        Entry = self.env['toggl.entry'].with_context(active_test=False)
        existing = {e.toggl_id: e for e in Entry.search([('start', '>=', self.start_date),('stop', '<=', self.end_date)])}
        _logger.info("Found %s existing toggl entries.", len(existing))
        for entry in entries:
            if not entry.get('stop'):
                continue # running entry

            toggl_id = entry['id']
            vals = {
                'toggl_name': entry['description'],
                'name': entry['description'],
                'start': date(entry['start']),
                'stop': date(entry['stop']),
                'duration': entry['duration']/(60*60),
            }
            if toggl_id in existing:
                existing[toggl_id].write(vals)
            else:
                existing[toggl_id] = Entry.with_context(default_toggl_id=toggl_id).create(vals)

            Entry += existing[toggl_id]

        for toggl_entries in existing.values():
            toggl_entries.recompute_depends()

        [action] = self.env.ref('toggl_sync.entry_action').read()
        return action