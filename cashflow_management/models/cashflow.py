# -*- coding: utf-8 -*-
import base64, traceback, logging
import tempfile
import subprocess

from odoo import api, models, fields, _
from odoo.exceptions import ValidationError
from odoo.tools import float_is_zero, float_compare

from odoo.tools.safe_eval import safe_eval, test_python_expr, wrap_module, datetime, dateutil
requests = wrap_module(__import__('requests'), ['get', 'post'])
io = wrap_module(__import__('io'), ['StringIO', 'BytesIO'])
pandas = wrap_module(__import__('pandas'), ['read_csv', 'read_excel'])
re = wrap_module(__import__('re'), ['findall',])


import lxml
lxml_mods = ['etree']
for mod in lxml_mods:
    __import__('lxml.%s' % mod)
lxml = wrap_module(__import__('lxml'), {mod: getattr(lxml, mod).__all__ for mod in lxml_mods})



import pdfminer
pdfminer_mods = {'high_level': ['extract_text_to_fp']}
for mod in pdfminer_mods:
    __import__('pdfminer.%s' % mod)
pdfminer = wrap_module(__import__('pdfminer'), {mod: pdfminer_mods[mod] for mod in pdfminer_mods})



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

    parser_id = fields.Many2one(comodel_name='cashflow.parser', required=True, store=True, readonly=False, compute='_compute_active_ids')
    account_id = fields.Many2one(comodel_name='cashflow.account', required=True, store=True, readonly=False, compute='_compute_active_ids')
    attachment_ids = fields.Many2many('ir.attachment', string='Files', required=True)

    @api.depends('parser_id', 'account_id')
    @api.depends_context('active_model', 'active_ids')
    def _compute_active_ids(self):
        ctx = self.env.context
        active_ids = ctx.get('active_ids', [])
        active_model = ctx.get('active_model', '')
        for record in self:
            if active_model == 'cashflow.parser' and active_ids:
                record.parser_id = active_ids[0]
                record.account_id = record.parser_id.account_ids[:1]
            if active_model == 'cashflow.parser' and active_ids:
                record.account_id = active_ids[0]
                record.parser_id = record.account_id.parser_ids[:1]


    def import_file(self):
        for attachment_id in self.attachment_ids:
            self.parse(attachment_id)

        self.attachment_ids.write({
            'res_model': self.parser_id._name,
            'res_id': self.parser_id.id,
        })

    def parse(self, attachment_id):
        self.ensure_one()
        attachment_id.ensure_one()

        data = base64.b64decode(attachment_id.datas)
        fp = io.BytesIO(data)
        def add_entry(vals):
            vals['account_id'] = self.account_id.id
            vals['parser_id'] = self.parser_id.id
            vals['attachment_id'] = attachment_id.id
            return self.env['cashflow.entry'].create(vals)

        globals_dict = {
            'ValidationError': ValidationError,
            'requests': requests,
            'datetime': datetime,
            'dateutil': dateutil,
            'lxml': lxml,
            'io': io,
            'self': self.env['cashflow.entry'],
            'fp': fp,
            'pandas': pandas,
            '_logger': _logger,
            'pdfminer': pdfminer,
            'pdftotext': pdftotext,
            're': re,
            'add_entry': add_entry,
        }
        safe_eval(self.parser_id.code, globals_dict=globals_dict, mode="exec", nocopy=True)




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


class CashflowCategory(models.Model):
    _name = 'cashflow.account'
    _description = 'Cash Flow Account'
    _order = 'sequence, id'

    name = fields.Char(required=True)
    sequence = fields.Integer(string='Sequence')

    parser_ids = fields.Many2many(comodel_name='cashflow.parser')

    active = fields.Boolean(default=True)

    entry_ids = fields.One2many(
        comodel_name='cashflow.entry',
        inverse_name='account_id',
        readonly=True,
    )

    _sql_constraints = [
        ('unique_name', 'unique(name)', 'This account already exists!'),
    ]


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

    active = fields.Boolean(related='account_id.active')
    account_id = fields.Many2one(
        comodel_name='cashflow.account',
        required=True,
        ondelete='restrict',
    )
    company_currency_id = fields.Many2one(related='company_id.currency_id', string="Company Currency", readonly=True)

    parser_id = fields.Many2one(comodel_name='cashflow.parser', required=True)
    raw = fields.Text(readonly=True)
    identifier = fields.Char(readonly=True)
    attachment_id = fields.Many2one(comodel_name='ir.attachment', ondelete='cascade', required=True, domain="[('res_model', '=', 'cashflow.parser'), ('res_id', '=', parser_id)]")
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