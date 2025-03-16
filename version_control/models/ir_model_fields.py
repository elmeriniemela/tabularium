
from odoo import api, models, fields


class MailTrackingValues(models.Model):
    _inherit = 'ir.model.fields'

    version_control = fields.Boolean()

    def _reflect_field_params(self, field, model_id):
        res = super()._reflect_field_params(field, model_id)
        res['version_control'] = getattr(field, 'version_control', False)
        return res