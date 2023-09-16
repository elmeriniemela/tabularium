# -*- coding: utf-8 -*-
from odoo import api, models, fields, _
from odoo.exceptions import ValidationError
from odoo.tools.safe_eval import test_python_expr




class Cashflowparser(models.Model):
    _name = 'cashflow.parser'
    _description = 'Cash Flow Parser'
    _order = 'sequence, id'

    name = fields.Char(required=True)
    sequence = fields.Integer(string='Sequence')
    code = fields.Text(required=True)

    entry_ids = fields.One2many(
        comodel_name='cashflow.entry',
        inverse_name='parser_id',
        readonly=True,
    )

    attachment_ids = fields.One2many(
        comodel_name='ir.attachment',
        inverse_name='res_id',
        domain=[('res_model', '=', _name)],
        string='Imported Files'
    )

    account_ids = fields.Many2many(comodel_name='cashflow.account')

    def delete_files(self):
        for parser in self:
            parser.attachment_ids.unlink()

    @api.constrains('code')
    def _validate_code(self):
        for record in self:
            msg = test_python_expr(expr=record.code.strip(), mode="exec")
            if msg:
                raise ValidationError(msg)
