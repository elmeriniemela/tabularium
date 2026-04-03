# -*- coding: utf-8 -*-

from odoo import api, models, fields, _
import logging

_logger = logging.getLogger(__name__)

class InvestmentPositionNote(models.Model):
    _name = 'investment.position.note'
    _description = 'Position Mote'
    _inherit = ['mail.thread']
    _order = "sequence, id"

    sequence = fields.Integer('Sequence', default=0)

    name = fields.Char(
        required=True,
        tracking=True,
    )

    content = fields.Html(
        tracking=True,
        sanitize=False,
        translate=False,
        version_control=True,
    )

    company_id = fields.Many2one(
        comodel_name='res.company',
        required=True,
        default=lambda self: self.env.company,
        index=True,
        tracking=True,
    )

    position_ids = fields.One2many(
        comodel_name='investment.position',
        inverse_name='thesis_id',
        context={'active_test': False},
        readonly=True,
    )

    move_ids = fields.One2many(
        comodel_name='investment.position.move',
        inverse_name='note_id',
        context={'active_test': False},
        readonly=True,
    )

    def action_documents(self):
        """ Open the documents linked to this note. """
        self.ensure_one()
        ctx = dict(self.env.context or {})
        action_xmlid = ctx.pop('action')
        action = self.env.ref(action_xmlid).read()[0]
        action['domain'] = [('id', 'in', ctx.pop('domain_ids'))]
        action['context'] = ctx
        return action


