# -*- coding: utf-8 -*-

import io
import base64
import logging
from decimal import Decimal
from odoo import fields, models, _
from odoo.exceptions import ValidationError
from .ibkr_parse import IBKRParser
_logger = logging.getLogger(__name__)

class InvestmentTransactionImport(models.Model):
    _name = 'investment.transaction.import'
    _description = 'Transaction Import'
    _inherit = ['mail.thread']
    _order = 'name desc'

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
        tracking=True,
    )

    company_id = fields.Many2one(
        comodel_name='res.company',
        required=True,
        default=lambda self: self.env.company,
        index=True,
        tracking=True,
    )

    portfolio_id = fields.Many2one(
        comodel_name='investment.portfolio',
        required=True,
        index=True,
        tracking=True,
    )

    validate_balances = fields.Boolean(
        tracking=True,
        default=True,
    )

    transaction_ids = fields.One2many(
        comodel_name='investment.position.transaction',
        inverse_name='import_id',
    )

    vals_list = fields.Json(
        compute='_compute_vals_list',
    )


    def _parse_ibkr(self):
        def currency_rate(code, date):
            rate = self.env['res.currency.rate'].search([
                ('currency_id.name', '=', code),
                ('name', '=', date),
            ])
            if not rate:
                raise ValidationError(_("Rate for %s on %s not found") % (code, date))
            return Decimal(rate.inverse_company_rate)

        if self.validate_balances:
            starting_balances = {
                p.name: Decimal(f'{quantity:.7f}') for p, quantity in self.env['investment.position.transaction'].sudo()._read_group(
                    domain=[
                        ('company_id', '=', self.company_id.id),
                        ('portfolio_id', '=', self.portfolio_id.id),
                        ('usage', '=', 'record'),
                        ('import_id.name', '<', self.name),
                    ],
                    groupby=['position_id'],
                    aggregates=['quantity:sum'],

                ) if quantity
            }
        else:
            starting_balances = None

        parser = IBKRParser(currency_rate, starting_balances)
        data = base64.b64decode(self.file).decode('utf-8-sig')
        buf = io.StringIO(data)
        try:
            rows = parser.extract_ledger_rows(buf)
        except ValueError as err:
            msg = f"{self.name}: {err.args[0]}"
            raise ValidationError(msg)

        vals_list = []
        for vals in rows:
            ticker = vals.pop('ticker')
            position = self.env['investment.position'].search([
                ('company_id', '=', self.company_id.id),
                ('portfolio_id', '=', self.portfolio_id.id),
                ('name', '=', ticker),
            ])
            if not position:
                raise ValidationError(_('Position not found: %s') % ticker)
            vals['position_id'] = position.id
            vals['quantity'] = float(vals['quantity'])
            vals['exchange_rate'] = float(vals['exchange_rate'])
            vals['payment_currency'] = float(vals['payment_currency'])
            vals_list.append(vals)
        return vals_list

    def _compute_vals_list(self):
        for record in self:
            record.vals_list = getattr(record, f'_parse_{record.source}')()

    def action_import(self):
        TX = self.env['investment.position.transaction']
        imported = self.mapped('transaction_ids')
        for rec in self:
            for vals in rec.vals_list:
                vals['import_id'] = rec.id
                xmlid = vals['external_ref']
                module = '__import__'
                tx = self.env.ref(f"{module}.{xmlid}", raise_if_not_found=False)
                if tx:
                    if tx.is_locked:
                        tx.write({k: v for k, v in vals.items() if k not in TX._get_locked_fields()})
                    else:
                        tx.write(vals)
                else:
                    tx = TX.create(vals)
                    self.env['ir.model.data'].sudo().create({
                        'name': xmlid,
                        'module': module,
                        'model': tx._name,
                        'res_id': tx.id,
                    })
                imported += tx
            rec.message_post(body=_("Import done."))

        return {
            'type': 'ir.actions.act_window',
            'name': _('Imported Transactions'),
            'res_model': imported._name,
            'view_mode': 'list',
            'context': {'search_default_move_not_set': 1},
            'views': [[False, 'list'], [False, 'form']],
            'domain': [('id', 'in', imported.ids)],
        }