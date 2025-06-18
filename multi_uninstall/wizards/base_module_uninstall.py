# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _


class BaseModuleUninstall(models.TransientModel):
    _inherit = "base.module.uninstall"


    def action_next(self):
        context = self.env.context.copy()
        active = self.env['ir.module.module'].browse(context.get('active_ids') or []).filtered(lambda m: m.state in ('installed', 'to upgrade') and m!=self.module_id).ids
        if len(active) > 1:
            context['default_show_all'] = True
            context['default_module_id'] = active[0]
            return {
                'name': _('Uninstall (%s left)') % len(active),
                'view_mode': 'form',
                'res_model': self._name,
                'type': 'ir.actions.act_window',
                'context': context,
                'target': 'new',
            }



    def action_uninstall(self):
        action = super().action_uninstall()
        return self.action_next() or action
