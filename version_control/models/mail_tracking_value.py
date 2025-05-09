
from odoo import api, models


class MailTrackingValues(models.Model):
    _inherit = 'mail.tracking.value'

    @api.model
    def _create_tracking_values(self, initial_value, new_value, col_name, col_info, record):
        """ Prepare values to create a mail.tracking.value. It prepares old and
        new value according to the field type.

        :param initial_value: field value before the change, could be text, int,
          date, datetime, ...;
        :param new_value: field value after the change, could be text, int,
          date, datetime, ...;
        :param str col_name: technical field name, column name (e.g. 'user_id);
        :param dict col_info: result of fields_get(col_name);
        :param <record> record: record on which tracking is performed, used for
          related computation e.g. finding currency of monetary fields;

        :return: a dict values valid for 'mail.tracking.value' creation;
        """
        field = self.env['ir.model.fields']._get(record._name, col_name)
        if not field:
            raise ValueError(f'Unknown field {col_name} on model {record._name}')
        values = {'field_id': field.id}
        if col_info['type'] == 'html' and field.version_control:
            values.update({
                f'old_value_text': initial_value,
                f'new_value_text': new_value
            })
            return values

        return super()._create_tracking_values(initial_value, new_value, col_name, col_info, record)


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
