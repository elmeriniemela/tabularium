# -*- coding: utf-8 -*-

import requests
from odoo import models, fields, api, _
from odoo.exceptions import UserError



class Toggl(models.AbstractModel):
    _name = 'toggl'
    _description = 'Toggl'

    @api.model
    def api_call(self, method, endpoint, **kwargs):
        api_token = self.env['ir.config_parameter'].sudo().get_param('toggl.api.token')
        response = getattr(requests, method)(
            f'https://api.track.toggl.com/api/v8/{endpoint}',
            headers={"content-type": "application/json"},
            auth=(api_token, "api_token"),
            timeout=10,
            **kwargs
        )
        if response.status_code != 200:
            raise UserError(
                _("Error from toggl:\nURL=%s\nSTATUS=%s\nMESSAGE=%s") %
                    (response.url, response.status_code, response.text)
            )
        return response.json()

    @api.model
    def time_entries(self, start_date, end_date):
        return self.api_call('get', 'time_entries', params={
            'start_date': fields.Datetime.context_timestamp(self, start_date).isoformat(),
            'end_date': fields.Datetime.context_timestamp(self, end_date).isoformat(),
        })


    @api.model
    def update_time_entry(self, time_entry_id, **kwargs):
        return self.api_call('put', f'time_entries/{time_entry_id}', **kwargs)
