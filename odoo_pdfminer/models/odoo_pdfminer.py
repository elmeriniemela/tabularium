# -*- coding: utf-8 -*-


import base64
import io
import pprint
import re
import dateutil

from pdfminer.high_level import extract_text_to_fp

from odoo import models, fields, api




class AccountMove(models.Model):
    _inherit = 'account.move'

    pdfminer_id = fields.Many2one(
        comodel_name='odoo.pdfminer',
        readonly=True,
    )




class OdooPDFMiner(models.Model):
    _name = 'odoo.pdfminer'
    _description = 'Odoo Pdf Miner'

    name = fields.Char(required=True)

    pdf_source = fields.Binary()

    pdf_source_filename = fields.Char()

    source_text = fields.Text(compute="_compute_source_text", store=True)

    re_amount_total = fields.Char(regex='amount_total')

    re_invoice_date = fields.Char(regex='invoice_date')

    re_ref = fields.Char(regex='ref')

    re_payment_ref = fields.Char(regex='invoice_payment_ref')

    product_id = fields.Many2one(
        comodel_name='product.product'
    )

    journal_id = fields.Many2one(
        comodel_name='account.journal',
    )

    partner_id = fields.Many2one(
        comodel_name='res.partner',
    )

    move_type = fields.Selection(
        selection=lambda self: self.env['account.move']._fields['type'].selection,
    )

    result = fields.Text(compute="_compute_result")

    move_ids = fields.One2many(
        comodel_name='account.move',
        inverse_name='pdfminer_id',
        readonly=True,
    )


    def _compute_result(self):
        for record in self:
            if record.source_text:
                record.result = pprint.pformat(record._get_pdf_vals(record.source_text))
            else:
                record.result = False

    def create_invoice(self):
        vals = self._get_pdf_vals(record.text)
        Move = self.env['account.move'].with_context(
            default_journal_id=vals['journal_id'],
            default_partner_id=vals['partner_id'],
            default_type=vals['type'],
        )
        invoices = Move.create(vals)
        return {
            'type': 'ir.actions.act_window',
            'name': "New invoices",
            'res_model': 'account.move',
            'domain': [('id', 'in', invoices.ids)],
            'view_mode': 'tree,form',
        }


    def _get_pdf_vals(self, text):
        self.ensure_one()
        vals = {
            'journal_id': self.journal_id.id,
            'partner_id': self.partner_id.id,
            'type': self.move_type,
            'pdfminer_id': self.id,
        }

        for fieldname, field in self._fields.items():
            if hasattr(field, 'regex') and self[fieldname]:
                matches = re.findall(self[fieldname], text)
                if matches:
                    vals[field.regex] = matches[0]

        total = vals.pop('amount_total', None)
        if total:
            vals['invoice_line_ids'] = [(0, 0, {
                'product_id': self.product_id.id,
                'quantity': 1.0,
                'price_unit': float(total.replace(',', '.')),
            })]

        invoice_date = vals.pop('invoice_date', None)
        if invoice_date:
            vals['invoice_date'] = dateutil.parser.parse(invoice_date).date()

        return vals


    def _pdf_to_text(self, raw_data):
        data = base64.b64decode(raw_data)
        inf = io.BytesIO(data)
        outfp = io.BytesIO()
        extract_text_to_fp(inf, outfp)
        outfp.seek(0)
        text = outfp.read()
        return text


    @api.depends('pdf_source')
    def _compute_source_text(self):
        for record in self:
            record.source_text = False
            raw_data = record.with_context(bin_size=False).pdf_source

            if not raw_data:
                continue


            record.source_text = record._pdf_to_text(raw_data)


