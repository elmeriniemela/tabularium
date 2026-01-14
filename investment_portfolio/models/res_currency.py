

from odoo import fields, models


class ResCurrency(models.Model):
    _inherit = "res.currency"

    asset_id = fields.Many2one(
        comodel_name='investment.asset',
    )
