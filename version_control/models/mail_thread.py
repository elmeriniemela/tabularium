
from odoo import api, models


class MailThread(models.AbstractModel):
    _inherit = 'mail.thread'


    def _valid_field_parameter(self, field, name):
        return name == 'version_control' and field.type == 'text' or super()._valid_field_parameter(field, name)

