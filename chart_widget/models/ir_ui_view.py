from odoo import fields, models


class View(models.Model):
    _inherit = 'ir.ui.view'

    type = fields.Selection(selection_add=[('chart', 'Chart')])

    def _get_view_info(self):
        return {'chart': {'icon': 'fa fa-line-chart'}} | super()._get_view_info()
