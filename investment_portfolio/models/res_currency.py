

from odoo import api, models, fields, Command, _
from odoo.exceptions import ValidationError


class ResCurrency(models.Model):
    _inherit = "res.currency"

    asset_id = fields.Many2one(
        comodel_name='investment.asset',
    )


class ResCurrencyRate(models.Model):
    _inherit = "res.currency.rate"

    is_locked = fields.Boolean(compute='_compute_is_locked')

    def _check_lock_time(self):
        for record in self:
            if record.is_locked:
                raise ValidationError(_("You cannot modify transaction entries (%s UTC) before the company lock time (%s UTC).") % (record.name, record.company_id.investment_lock_time))

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._check_lock_time()
        return records

    def write(self, vals):
        self._check_lock_time()
        result = super().write(vals)
        self._check_lock_time()
        return result

    def unlink(self):
        self._check_lock_time()
        return super().unlink()

    @api.depends('company_id.investment_lock_time', 'name')
    def _compute_is_locked(self):
        for record in self:
            if not record.company_id.investment_lock_time:
                record.is_locked = False
                continue
            date = fields.Datetime.context_timestamp(
                record.with_context(tz=record.company_id.partner_id.tz),
                record.company_id.investment_lock_time,
            ).date()
            record.is_locked = bool(record.name <= date)
