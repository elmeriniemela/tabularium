# -*- coding: utf-8 -*-

from odoo import api, models, fields, _
from odoo.exceptions import ValidationError
import requests, datetime, traceback, logging, dateutil, lxml.etree, io
from odoo.tools.safe_eval import safe_eval, test_python_expr
from odoo.tools import float_is_zero, float_compare


_logger = logging.getLogger(__name__)


class CashflowCategory(models.Model):
    _name = 'cashflow.category'
    _description = 'Cash Flow Category'

    name = fields.Char(required=True)


class Cashflowparser(models.Model):
    _name = 'cashflow.parser'
    _description = 'Cash Flow Parser'

    name = fields.Char(required=True)
    code = fields.Text(required=True)

    entry_ids = fields.One2many(
        comodel_name='cashflow.entry',
        inverse_name='parser_id',
        readonly=True,
    )

    @api.constrains('code')
    def _validate_code(self):
        for record in self:
            msg = test_python_expr(expr=record.code.strip(), mode="exec")
            if msg:
                raise ValidationError(msg)

    def execute(self):
        self.ensure_one()
        globals_dict = {
            'ValidationError': ValidationError,
            'requests': requests,
            'datetime': datetime,
            'dateutil': dateutil,
            'lxml': lxml,
            'io': io,
            'self': self,
        }
        safe_eval(self.code, globals_dict=globals_dict, mode="exec", nocopy=True)

class CashflowEntry(models.Model):
    _name = 'cashflow.entry'
    _description = 'Cash Flow Entry'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(required=True)
    date = fields.Date(required=True, default=fields.Date.today)
    amount = fields.Monetary(required=True, currency_field='company_currency_id')
    company_id = fields.Many2one(comodel_name='res.company', required=True, default=lambda self: self.env.company)
    category_id = fields.Many2one(comodel_name='cashflow.category', required=True)
    company_currency_id = fields.Many2one(related='company_id.currency_id', string="Company Currency")
    parser_id = fields.Many2one(comodel_name='cashflow.parser')

