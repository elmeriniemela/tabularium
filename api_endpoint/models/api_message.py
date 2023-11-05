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
        ],
        required=True,
        tracking=True,
        default='produced',
    )

    content = fields.Binary()

    endpoint_id = fields.Many2one(
        comodel_name='api.endpoint',
        required=True,
        ondelete='cascade',
        index=True
    )

    preview = fields.Text(
        string="Content Preview",
        compute='_compute_preview',
    )


    def _compute_preview(self):
        for record in self:
            preview = False
            if record.endpoint_id.file_format in ['json', 'xml', 'csv']:
                content = record.with_context(bin_size=False).content
                if content:
                    preview = base64.b64decode(content)
            record.preview = preview


    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            endpoint_id = vals.get('endpoint_id') or self.env.context.get('default_endpoint_id')
            if endpoint_id:
                endpoint = self.env['api.endpoint'].browse(endpoint_id)
                if 'name' not in vals:
                    vals['name'] = '%s.%s' % (endpoint.sequence_id.next_by_id(), endpoint.file_format)
        return super().create(vals_list)
