# -*- coding: utf-8 -*-

import logging
import dateutil
import pytz

from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class TogglImport(models.TransientModel):
    _name = 'toggl.import'
    _description = 'Toggl Import'

    start_date = fields.Datetime(
        required=True,
        default=lambda self: self.env['toggl.entry'].search([], limit=1).stop
    )

    end_date = fields.Datetime(
        required=True,
        default=fields.Datetime.now
    )

    def import_entries(self):
        entries = self.env['toggl'].time_entries(self.start_date, self.end_date)

        date = lambda dt_str: dateutil.parser.parse(dt_str).astimezone(pytz.utc).replace(tzinfo=None)

        Entry = self.env['toggl.entry'].with_context(active_test=False)
        existing = {e.toggl_id: e for e in Entry.search([])}
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

        [action] = self.env.ref('toggl_sync.entry_action').read()
        return action