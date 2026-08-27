
from odoo import fields, models

from bitwalkit import NodeRPC


class BigInteger(fields.Integer):
    column_type = ('int8', 'int8')

class ConfigParam(models.Model):
    _inherit = 'ir.config_parameter'

    def bitcoind_proxy(self):
        get_param = self.env['ir.config_parameter'].sudo().get_param
        return NodeRPC(
            get_param('bitcoind.url'),
            get_param('bitcoind.user'),
            get_param('bitcoind.pw'),
        )

fields.BigInteger = BigInteger
