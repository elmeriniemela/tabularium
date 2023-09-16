# -*- coding: utf-8 -*-
import base64, logging
import tempfile
import subprocess

from odoo import api, models, fields, _
from odoo.exceptions import ValidationError

from odoo.tools.safe_eval import safe_eval, wrap_module, datetime, dateutil
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
            if active_model == 'cashflow.account' and active_ids:
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



