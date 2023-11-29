# -*- coding: utf-8 -*-

import logging
import base64
from odoo import models, tools, fields, api, _

_logger = logging.getLogger(__name__)


class ApiMessage(models.Model):
    _name = 'api.message'
    _description = 'API Message'
    _inherit = ['mail.thread']
    _order = 'name desc, id desc'

    name = fields.Char(required=True, index=True)

    context = fields.Char(required=True, default=lambda self: str(self.env.context))

    params = fields.Char(required=True, default='{}')

    state = fields.Selection(
        selection=[
            ('produced', 'Produced'),
            ('consumed', 'Consumed'),
            ('error', 'Error'),
        ],
        required=True,
        tracking=True,
        default='produced',
    )

    content = fields.Binary()
    response = fields.Binary()

    endpoint_id = fields.Many2one(
        comodel_name='api.endpoint',
        required=True,
        ondelete='cascade',
        index=True
    )

    content_preview = fields.Text(
        string="Content Preview",
        compute='_compute_content_preview',
    )

    response_preview = fields.Text(
        string="Response Preview",
        compute='_compute_response_preview',
    )

    def _compute_response_preview(self):
        for record in self.with_context(bin_size=False):
            response_preview = False
            if record.endpoint_id.response_format in ['json', 'xml', 'csv']:
                response = record.response
                if response:
                    response_preview = base64.b64decode(response)
            record.response_preview = response_preview


    def _compute_content_preview(self):
        for record in self.with_context(bin_size=False):
            content_preview = False
            if record.endpoint_id.file_format in ['json', 'xml', 'csv']:
                content = record.content
                if content:
                    content_preview = base64.b64decode(content)
            record.content_preview = content_preview


    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            endpoint_id = vals.get('endpoint_id') or self.env.context.get('default_endpoint_id')
            if endpoint_id:
                endpoint = self.env['api.endpoint'].browse(endpoint_id)
                if 'name' not in vals:
                    vals['name'] = '%s.%s' % (endpoint.sequence_id.next_by_id(), endpoint.file_format)
        return super().create(vals_list)
