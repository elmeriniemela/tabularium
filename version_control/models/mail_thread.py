
from odoo import api, models, fields


class MailThread(models.AbstractModel):
    _inherit = 'mail.thread'

    version_control_ids = fields.One2many(
        comodel_name='version.control',
        inverse_name='res_id',
        string='Version Control',
        domain=lambda self: [('model', '=', self._name)],
        auto_join=True,
    )

    version_control_count = fields.Integer(
        string='Versions',
        compute='_compute_version_control_count',
    )

    def _compute_version_control_count(self):
        for rec in self:
            rec.version_control_count = len(rec.version_control_ids)

    def _valid_field_parameter(self, field, name):
        return name == 'version_control' and field.type == 'text' or super()._valid_field_parameter(field, name)

