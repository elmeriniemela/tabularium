# -*- coding: utf-8 -*-

import logging
import requests
import dateutil
import pytz

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class TogglImport(models.TransientModel):
    _name = 'toggl.import'
    _description = 'Toggl Import'

    api_token = fields.Char(required=True)

    start_date = fields.Datetime(
        required=True,
        default=lambda self: self.env['toggl.entry'].search([], limit=1).stop
    )

    end_date = fields.Datetime(
        required=True,
        default=fields.Datetime.now
    )

    def import_entries(self):
        response = requests.get(
            'https://api.track.toggl.com/api/v8/time_entries',
            headers={"content-type": "application/json"},
            auth=(self.api_token, "api_token"),
            params={
                'start_date': fields.Datetime.context_timestamp(self, self.start_date).isoformat(),
                'end_date': fields.Datetime.context_timestamp(self, self.end_date).isoformat(),
            },
            timeout=10,
        )
        if response.status_code != 200:
            raise UserError(response.text)

        date = lambda dt_str: dateutil.parser.parse(dt_str).astimezone(pytz.utc).replace(tzinfo=None)

        Entry = self.env['toggl.entry']
        existing = {e.toggl_id: e for e in Entry.search([])}
        for entry in response.json():
            toggl_id = entry['id']
            vals = {
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