# -*- coding: utf-8 -*-

import logging
from odoo import models, api, fields, exceptions, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class CloudServerDiff(models.Model):
    _name = 'cloud.server.diff'
    _description = 'Cloud Server Diff'

    name = fields.Char(
        required=True,
        compute='_compute_name',
        store=True,
        readonly=False,
    )

    diff = fields.Text(readonly=True)

    server_id = fields.Many2one(
        string="Server",
        comodel_name='cloud.server',
        required=True,
        index=True,
        ondelete='cascade',
    )

    allow_update = fields.Boolean(
        compute='_compute_allow_update'
    )

    @api.depends('diff')
    def _compute_allow_update(self):
        for record in self:
            record.allow_update = bool(record.diff)

    @api.depends('server_id')
    def _compute_name(self):
        for record in self:
            s = record.server_id
            record.name = record.name or f'{s.commit.strip()}...origin/{s.branch.strip()}'

    def action_fetch_diff(self):
        s = self.server_id
        self.diff = s._rpc(method='agent_diff', args=(self.name.strip(),))
        if not self.diff:
            raise ValidationError(_("No changes."))

        return {
            'type': 'ir.actions.act_window',
            'name': _('Diff'),
            'view_mode': 'form',
            'res_model': self._name,
            'target': 'current',
            'res_id': self.id,
            'views': [[False, 'form']],
        }

    def action_update_server(self):
        if not self.allow_update:
            raise ValidationError(_("Not allowed to update from this diff."))
        s = self.server_id
        s.instance_ids.restart_needed = True
        s.commit = s._rpc(method='agent_pull', args=(s.branch,))
        s.action_agent_restart()
