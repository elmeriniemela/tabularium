

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    consumption_position_id = fields.Many2one(
        comodel_name='investment.position',
    )

    cash_position_id = fields.Many2one(
        comodel_name='investment.position',
    )
