# -*- coding: utf-8 -*-
import xmlrpc.client
import urllib.parse
import requests
from odoo import models, fields, api, _
from odoo.exceptions import UserError

TOGGL_SELF = [
    'toggl_api_token',
    'toggl_export_url',
    'toggl_export_dbname',
    'toggl_export_uid',
    'toggl_export_pwd',
]

class ResUsers(models.Model):
    _inherit = 'res.users'

    toggl_api_token = fields.Char()
    toggl_export_url = fields.Char()
    toggl_export_dbname = fields.Char()
    toggl_export_uid = fields.Char()
    toggl_export_pwd = fields.Char()

    @property
    def SELF_READABLE_FIELDS(self):
        return super().SELF_READABLE_FIELDS + list(TOGGL_SELF)

    @property
    def SELF_WRITEABLE_FIELDS(self):
        return super().SELF_WRITEABLE_FIELDS + list(TOGGL_SELF)


    def _get_toggl_export_proxy(self):
        self.ensure_one()
        url = self.toggl_export_url
        dbname = self.toggl_export_dbname
        uid = self.toggl_export_uid
        pwd = self.toggl_export_pwd

        if not all([url, dbname, uid, pwd]):
            raise UserError(_("Export credentials not configured."))

        return xmlrpc.client.ServerProxy(urllib.parse.urljoin(url, '/xmlrpc/object')), dbname, uid, pwd

    def toggl_api_call(self, method, endpoint, **kwargs):
        api_token = self.toggl_api_token
        response = getattr(requests, method)(
            f'https://api.track.toggl.com/api/v9/me/{endpoint}',
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

    def toggl_time_entries(self, start_date, end_date):
        return self.toggl_api_call('get', 'time_entries', params={
            'start_date': fields.Datetime.context_timestamp(self, start_date).isoformat(),
            'end_date': fields.Datetime.context_timestamp(self, end_date).isoformat(),
        })


