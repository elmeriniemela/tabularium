
from odoo import api, models


class MailTrackingValues(models.Model):
    _inherit = 'mail.tracking.value'


    def _tracking_value_format_model(self, model):
        formatted = super()._tracking_value_format_model(model)
        for vals in formatted:
            tracking = self.browse(vals['id'])
            if tracking.field_id.version_control:
                version = self.env['version.control'].browse(vals['id']).exists()
                if version:
                    vals['oldValue']['value'] = version.version_hash_before
                    vals['newValue']['value'] = version.version_hash_after

        return formatted
