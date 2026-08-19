# -*- coding: utf-8 -*-

import logging
import base64
from odoo.addons.api_endpoint.models.api_endpoint import safe_eval
from odoo import models, tools, fields, api, _

_logger = logging.getLogger(__name__)


class ApiMessage(models.Model):
    _name = 'api.message'
    _description = 'API Message'
    _inherit = ['mail.thread']
    _order = 'id desc'

    name = fields.Char(required=True, index=True)

    context = fields.Char(required=True, default='{}')

    variables = fields.Char(required=True, default='{}')

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
            if record.endpoint_id.response_format in ['json', 'xml', 'csv', 'bytes']:
                response = record.response
                if response:
                    try:
                        response_preview = base64.b64decode(response)
                    except: # pragma: no cover
                        pass
            record.response_preview = response_preview


    def _compute_content_preview(self):
        for record in self.with_context(bin_size=False):
            content_preview = False
            if record.endpoint_id.file_format in ['json', 'xml', 'csv', 'bytes']:
                content = record.content
                if content:
                    try:
                        content_preview = base64.b64decode(content)
                    except: # pragma: no cover
                        pass
            record.content_preview = content_preview


    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            endpoint_id = vals.get('endpoint_id') or self.env.context.get('default_endpoint_id')
            if endpoint_id:
                endpoint = self.env['api.endpoint'].browse(endpoint_id)
                if 'name' not in vals:
                    vals['name'] = '%s.%s' % (endpoint.sequence_id.next_by_id(), endpoint.file_format)
        msgs = super().create(vals_list)
        for msg in msgs:
            msg.message_subscribe(msg.endpoint_id.message_follower_ids.mapped('partner_id.id'))
        return msgs

    def _get_msg_globals(msg):
        # READ-ONLY, should be OK not to ROLLBACK
        literal_globals = msg.endpoint_id._get_globals()

        context = safe_eval(msg.context, literal_globals)
        context['bin_size'] = False
        msg = msg.with_context(context)

        variables = safe_eval(msg.variables, literal_globals)
        globals_dict = msg.endpoint_id._get_globals()
        globals_dict.update(variables)
        obj = msg.endpoint_id.bytes_to_obj(base64.b64decode(msg.content), msg.endpoint_id.file_format)
        globals_dict['obj'] = obj
        globals_dict.force_set('msg', msg)
        return globals_dict

    def action_consume(self):
        for msg in self:
            globals_dict = msg._get_msg_globals()
            msg.endpoint_id._consume(globals_dict)
