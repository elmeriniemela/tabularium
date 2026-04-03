# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
import logging
import tempfile
import base64
import datetime
import html
from markupsafe import Markup
from odoo.tools import misc, float_is_zero
from dateutil.relativedelta import relativedelta
from py3o.template import Template
import json
import warnings


FILETYPE_BASE64_MAGICWORD = {
    b'/': 'jpg',
    b'R': 'gif',
    b'i': 'png',
    b'P': 'svg+xml',
}

_logger = logging.getLogger(__name__)


def tmp_odt():
    return tempfile.NamedTemporaryFile(mode='w+b', suffix='odt')


def format_multiline_value(value):
    if value:
        return Markup(
            html.escape(value)
            .replace("\n", "<text:line-break/>")
            .replace("\t", "<text:s/><text:s/><text:s/><text:s/>")
        )
    return ""

class AccountFiscalYear(models.Model):
    _name = 'account.fiscal.year'
    _description = 'Fiscal Year'
    _inherit = ['mail.thread',]

    name = fields.Char(
        string='Name',
        required=True,
    )
    date_from = fields.Date(
        string='Start Date',
        required=True,
        help='Start Date, included in the fiscal year.',
    )
    date_to = fields.Date(
        string='End Date',
        required=True,
        help='Ending Date, included in the fiscal year.',
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
    financials_template_id = fields.Many2one(
        comodel_name='ir.attachment',
        copy=True,
    )

    financials_signature = fields.Binary(copy=True)
    financials_signature2 = fields.Binary(
        related='financials_signature',
        string='Financial Signature 2',
    )
    logo_ftype = fields.Char(compute='_compute_logo_ftype')

    format_date_from = fields.Char(compute='_compute_format_date')
    format_date_from_previous = fields.Char(compute='_compute_format_date')
    format_date_to = fields.Char(compute='_compute_format_date')
    format_date_to_previous = fields.Char(compute='_compute_format_date')
    format_date_expire = fields.Char(compute='_compute_format_date')

    place_and_date = fields.Char(compute='_compute_place_and_date')

    @api.constrains('date_from', 'date_to', 'company_id')
    def _check_dates(self):
        for rec in self:
            date_from = rec.date_from
            date_to = rec.date_to
            if date_to < date_from:
                raise ValidationError(_('The ending date must not be prior to the starting date.'))
            if rec.company_id.parent_id:
                raise ValidationError(_('You cannot have a fiscal year on a child company.'))

            domain = [
                ('id', '!=', rec.id),
                ('company_id', '=', rec.company_id.id),
                '|', '|',
                '&', ('date_from', '<=', rec.date_from), ('date_to', '>=', rec.date_from),
                '&', ('date_from', '<=', rec.date_to), ('date_to', '>=', rec.date_to),
                '&', ('date_from', '<=', rec.date_from), ('date_to', '>=', rec.date_to),
            ]

            if self.search_count(domain) > 0:
                raise ValidationError(_('You can not have an overlap between two fiscal years, please correct the start and/or end dates of your fiscal years.'))

    def copy(self, default=None):
        default = default or {
            'date_from': self.date_from+relativedelta(years=1),
            'date_to': self.date_to+relativedelta(years=1),
            'name': self.name + ' (copy)',
        }
        return super().copy(default)


    def _compute_place_and_date(self):
        for record in self:
            record.place_and_date = f'{record.company_id.city}, {misc.format_date(record.env, fields.Date.today())}'

    def _compute_format_date(self):
        for record in self:
            record.format_date_from = misc.format_date(record.env, record.date_from)
            record.format_date_from_previous = misc.format_date(record.env, record.date_from - relativedelta(years=1))
            record.format_date_to = misc.format_date(record.env, record.date_to)
            record.format_date_to_previous = misc.format_date(record.env, record.date_to - relativedelta(years=1))
            record.format_date_expire = misc.format_date(record.env, record.date_to + relativedelta(years=10))

    def _compute_logo_ftype(self):
        # py3o.image(objects.company_id.logo, objects.logo_ftype, height='4.0cm', isb64=True, keep_ratio=True)
        for record in self:
            record.logo_ftype = FILETYPE_BASE64_MAGICWORD.get((record.company_id.logo or '')[:1], 'png')


    def render_financials(self):
        with tmp_odt() as infile, tmp_odt() as outfile:
            infile.write(base64.b64decode(self.financials_template_id.datas))
            infile.seek(0)
            t = Template(infile.name, outfile.name)
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=DeprecationWarning)
                t.render(dict(
                    objects=self,
                    format_multiline_value=format_multiline_value,
                ))

            outdata = outfile.read()

        self.env['ir.attachment'].create({
            'name': f"{self.name}-{datetime.datetime.now().strftime('%Y-%m-%dT%H-%M-%S')}.odt",
            'res_model': self._name,
            'res_id': self.id,
            'type': 'binary',
            'datas': base64.b64encode(outdata)
        })

    def py3o_display_address(self):
        return self.company_id.partner_id._display_address(without_company=True)

    def py3o_pl_lines(self):
        return self._map_xml_id_to_lines('l10n_fi_reports.account_financial_report_l10n_fi_pl')

    def py3o_bs_lines(self):
        return self._map_xml_id_to_lines('l10n_fi_reports.account_financial_report_l10n_fi_bs')

    def _map_xml_id_to_lines(self, report_xml_id):
        fname_map = {
            'l10n_fi_reports.account_financial_report_l10n_fi_pl': 'account_financials/tests/pl.json',
            'l10n_fi_reports.account_financial_report_l10n_fi_bs': 'account_financials/tests/bs.json',
        }
        report = self.env.ref(report_xml_id, raise_if_not_found=False)
        if report: # pragma: no cover
            lines = self._get_report_lines(report)
        else:
            with misc.file_open(fname_map[report_xml_id], 'r') as bs:
                lines = json.load(bs)
            for vals in lines:
                vals['name'] = Markup(vals['name'])
        return lines

    def _get_report_lines(self, report): # pragma: no cover
        self.ensure_one()
        options = {'date': {}}
        options['date']['filter'] = 'custom'
        options['date']['date_from'] = self.date_from
        options['date']['date_to'] = self.date_to
        options['date']['mode'] = 'range'
        options['date']['period_type'] = 'fiscalyear'
        options['comparison'] = {'filter': 'same_last_year', 'number_period': 1}
        options['selected_analytic_account_names'] = []
        options['unfold_all'] = False
        options['export_mode'] = 'file'
        options['all_entries'] = False # Do not include unposted entries, 14.0
        options = report.get_options(options)
        all_column_groups_expression_totals = report._compute_expression_totals_for_each_column_group(
            report.line_ids.expression_ids,
            options,
        )
        lines = report._get_lines(options, all_column_groups_expression_totals)

        py3o_lines = []
        for line in lines:
            line_level = line.get('level') or 0
            line_name = line.get('name') or ''
            vals = {
                'name': Markup(
                    f"<text:s text:c=\"{line_level}\"/>{line_name}"
                )
            }
            for i, col_dict in enumerate(line['columns'][:2]):
                value = col_dict['name']
                if isinstance(value, float) and float_is_zero(value, precision_rounding=self.company_id.currency_id.rounding):
                    value = 0
                vals[f"col_{i + 1}"] = value

            py3o_lines.append(vals)
        return py3o_lines




