# -*- coding: utf-8 -*-

from odoo import api, models, fields, _

class CashflowCategory(models.Model):
    _name = 'cashflow.category'
    _description = 'Cash Flow Category'

    name = fields.Char(required=True)

    entry_ids = fields.One2many(
        comodel_name='cashflow.entry',
        inverse_name='category_id',
        readonly=True,
    )

    _sql_constraints = [
        ('unique_name', 'unique(name)', 'This category already exists!'),
    ]

    def sanitize(self):
        for record in self:
            record.name = record._get_sanitized(record.name)

    @staticmethod
    def _get_sanitized(name):
        return name.strip().lower().capitalize()

    def getsert(self, name):
        name = self._get_sanitized(name)
        category = self.search([('name', '=', name)], limit=1)
        if not category:
            category = self.create({'name': name})
        return category
