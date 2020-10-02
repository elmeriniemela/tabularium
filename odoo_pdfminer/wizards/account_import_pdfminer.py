# -*- coding: utf-8 -*-

import base64
import io
from lxml import etree

from odoo import api, fields, models, _
from odoo.exceptions import UserError

import logging
_logger = logging.getLogger(__name__)


class AccountPDFminerImport(models.TransientModel):
    _name = 'account.pdfminer.import'
    _description = 'Import pdfminer'

    attachment_ids = fields.Many2many(
        comodel_name='ir.attachment',
        string='Files',
        required=True,
         help='Get you eInvoices in electronic XML format and select them here.')




    def import_file(self):
        invoices = self.env['account.move']
        for i, data_file in enumerate(self.attachment_ids, start=1):
            _logger.info("Importing (%d/%d): %s", i, len(self.attachment_ids), data_file.name)
            data = base64.b64decode(data_file.datas)
            invoices |= self.env['account.move'].parse_pdfminer(data)
        return {
            'type': 'ir.actions.act_window',
            'name': "New invoices",
            'res_model': 'account.move',
            'domain': [('id', 'in', invoices.ids)],
            'view_mode': 'tree,form',
        }