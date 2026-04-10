# -*- coding: utf-8 -*-

from odoo import fields, models
from .ibkr_parse import IBKRParser

class InvestmentTransactionImport(models.Model):
    _name = 'investment.transaction.import'
    _description = 'Transaction Import'
    _inherit = ['mail.thread']
    _order = 'id desc'

    name = fields.Char(
        required=True,
        tracking=True,
    )

    file = fields.Binary(required=True)

    source = fields.Selection(
        selection=[
            ('ibkr', 'IBKR'),
        ],
        default='ibkr',
        required=True,
    )

    company_id = fields.Many2one(
        comodel_name='res.company',
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )

    transaction_ids = fields.One2many(
        comodel_name='investment.position.transaction',
        inverse_name='import_id',
    )

    vals_list = fields.Json(
        compute='_compute_vals_list',
    )


    def _parse_ibkr(self):
        return []

    def _compute_vals_list(self):
        for record in self:
            record.vals_list = getattr(record, f'_parse_{record.source}')()

    def action_import(self):
        TX = self.env['investment.position.transaction']
        for rec in self:
            for vals in rec.vals_list:
                vals['import_id'] = rec.id
                tx = self.env.ref(vals['id'], raise_if_not_found=False)
                if tx:
                    tx.write(vals)
                else:
                    tx = TX.create(vals)
