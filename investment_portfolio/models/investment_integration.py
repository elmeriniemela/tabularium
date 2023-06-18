# -*- coding: utf-8 -*-

from odoo import api, models, fields, _
from odoo.exceptions import ValidationError

from odoo.tools.safe_eval import safe_eval, test_python_expr, wrap_module, datetime, dateutil

import lxml
lxml_mods = ['etree']
for mod in lxml_mods:
    __import__('lxml.%s' % mod)
lxml = wrap_module(__import__('lxml'), {mod: getattr(lxml, mod).__all__ for mod in lxml_mods})

requests = wrap_module(__import__('requests'), ['get', 'post'])
io = wrap_module(__import__('io'), ['StringIO', 'BytesIO'])
pandas = wrap_module(__import__('pandas'), ['read_csv', 'read_excel'])


class InvestmentIntegration(models.Model):
    _name = 'investment.integration'
    _description = 'Investment Integration'

    name = fields.Char(required=True)
    code = fields.Text(required=True)

    @api.constrains('code')
    def _validate_code(self):
        for record in self:
            msg = test_python_expr(expr=record.code.strip(), mode="exec")
            if msg:
                raise ValidationError(msg)

    def execute(self, asset):
        self.ensure_one()
        globals_dict = {
            'ValidationError': ValidationError,
            'requests': requests,
            'datetime': datetime,
            'dateutil': dateutil,
            'lxml': lxml,
            'io': io,
            'pandas': pandas,
            'self': asset,
        }
        safe_eval(self.code, globals_dict=globals_dict, mode="exec", nocopy=True)

