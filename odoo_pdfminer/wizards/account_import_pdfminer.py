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

    pdfminer_id = fields.Many2one(
        comodel_name='odoo.pdfminer',
        readonly=True,
        default=lambda self: self.env.context.get('active_model') == 'odoo.pdfminer' and  self.env.context.get('active_id'),
        required=True,
    )

    attachment_ids = fields.Many2many(
        comodel_name='ir.attachment',
        string='Files',
        required=True,
    )




    def import_file(self):
        return self.pdfminer_id.create_invoice(self.attachment_ids)