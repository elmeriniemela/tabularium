# -*- coding: utf-8 -*-

from odoo import api, models, fields, _
from odoo.exceptions import ValidationError
import requests, datetime, traceback, logging, dateutil, lxml.etree, io
from odoo.tools.safe_eval import safe_eval, test_python_expr
from odoo.tools import float_is_zero, float_compare
import pandas
import base64
import pdfminer
import pdfminer.high_level
import re
import tempfile
import subprocess


def pdftotext(fp):
    pdfData = fp.read()
    tf = tempfile.NamedTemporaryFile()
    tf.write(pdfData)
    tf.seek(0)
    outputTf = tempfile.NamedTemporaryFile()

    if (len(pdfData) > 0) :
        out, err = subprocess.Popen(["pdftotext", "-layout", tf.name, outputTf.name ]).communicate()
        return outputTf.read()
    else:
        return b""

_logger = logging.getLogger(__name__)


class CashflowImport(models.TransientModel):
    _name = 'cashflow.import'
    _description = 'Cash Flow Import'

    parser_id = fields.Many2one(comodel_name='cashflow.parser', required=True, default=lambda self: self.env.context.get('active_id'))
    attachment_ids = fields.Many2many('ir.attachment', string='Files', required=True)

    def import_file(self):
        for attachment_id in self.attachment_ids:
            data = base64.b64decode(attachment_id.datas)
            fp = io.BytesIO(data)
            self.parser_id.parse(fp, attachment_id)

        self.attachment_ids.write({
            'res_model': self.parser_id._name,
            'res_id': self.parser_id.id,
        })
        self.parser_id.apply_account()


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

    attachment_ids = fields.One2many(
        comodel_name='ir.attachment',
        inverse_name='res_id',
        domain=[('res_model', '=', _name)],
        string='Imported Files'
    )

    account_id = fields.Many2one(
        comodel_name='cashflow.account',
        required=True,
        ondelete='restrict',
    )

    def apply_account(self):
        for record in self:
            to_update = record.env['cashflow.entry'].search([
                ('parser_id', '=', record.id),
                ('account_id', '!=', record.account_id.id)
            ])
            to_update.write({'account_id': record.account_id.id})

    def delete_files(self):
        for parser in self:
            parser.attachment_ids.unlink()

    @api.constrains('code')
    def _validate_code(self):
        for record in self:
            msg = test_python_expr(expr=record.code.strip(), mode="exec")
            if msg:
                raise ValidationError(msg)

    def parse(self, fp, attachment_id):
        self.ensure_one()
        globals_dict = {
            'ValidationError': ValidationError,
            'requests': requests,
            'datetime': datetime,
            'dateutil': dateutil,
            'lxml': lxml,
            'io': io,
            'self': self,
            'fp': fp,
            'attachment_id': attachment_id,
            'pandas': pandas,
            '_logger': _logger,
            'pdfminer': pdfminer,
            'pdftotext': pdftotext,
            're': re,
            'print': print,
        }
        safe_eval(self.code, globals_dict=globals_dict, mode="exec", nocopy=True)


class CashflowCategory(models.Model):
    _name = 'cashflow.account'
    _description = 'Cash Flow Account'

    name = fields.Char(required=True)

    _sql_constraints = [
        ('unique_name', 'unique(name)', 'This account already exists!'),
    ]


class CashflowCategory(models.Model):
    _name = 'cashflow.category'
    _description = 'Cash Flow Category'

    name = fields.Char(required=True)

    _sql_constraints = [
        ('unique_name', 'unique(name)', 'This category already exists!'),
    ]

    def getsert(self, name):
        category = self.search([('name', '=', name)], limit=1)
        if not category:
            category = self.create({'name': name})
        return category

class CashflowEntry(models.Model):
    _name = 'cashflow.entry'
    _description = 'Cash Flow Entry'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc'

    name = fields.Char(required=True)
    date = fields.Date(required=True, default=fields.Date.today)
    amount = fields.Monetary(required=True, currency_field='company_currency_id')

    company_id = fields.Many2one(comodel_name='res.company', required=True, default=lambda self: self.env.company)
    category_id = fields.Many2one(comodel_name='cashflow.category', required=True)
    account_id = fields.Many2one(
        comodel_name='cashflow.account',
        required=False,
        ondelete='set null',
    )
    company_currency_id = fields.Many2one(related='company_id.currency_id', string="Company Currency", readonly=True)

    parser_id = fields.Many2one(comodel_name='cashflow.parser')
    raw = fields.Text(readonly=True)
    identifier = fields.Char(readonly=True)
    attachment_id = fields.Many2one(comodel_name='ir.attachment', ondelete='cascade', readonly=True)
    entry_type = fields.Selection(
        selection=[
            ('deposit', 'Deposit'),
            ('withdrawal', 'Withdrawal'),
        ],
        compute='_compute_entry_type',
        store=True,
    )

    _sql_constraints = [
        ('zero_amount', 'CHECK(amount != 0)', 'Amount can not be zero!'),
    ]

    @api.depends('amount')
    def _compute_entry_type(self):
        for record in self:
            record.entry_type = 'deposit' if record.amount > 0 else 'withdrawal'