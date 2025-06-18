# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
import logging
import tempfile
import base64
import datetime
import html
from markupsafe import Markup
from odoo.tools import misc, float_is_zero
from dateutil.relativedelta import relativedelta

FILETYPE_BASE64_MAGICWORD = {
    b'/': 'jpg',
    b'R': 'gif',
    b'i': 'png',
    b'P': 'svg+xml',
}

_logger = logging.getLogger(__name__)

try:
    from py3o.template import Template
except ImportError as error:
    _logger.error(error)

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
    _inherit = [_name, 'mail.thread']

    financials_template_id = fields.Many2one(
        comodel_name='ir.attachment',
        copy=True)

    financials_signature = fields.Binary(copy=True)
    financials_signature2 = fields.Binary(related='financials_signature')

    logo_ftype = fields.Char(compute='_compute_logo_ftype')

    format_date_from = fields.Char(compute='_compute_format_date')
    format_date_from_previous = fields.Char(compute='_compute_format_date')
    format_date_to = fields.Char(compute='_compute_format_date')
    format_date_to_previous = fields.Char(compute='_compute_format_date')
    format_date_expire = fields.Char(compute='_compute_format_date')

    place_and_date = fields.Char(compute='_compute_place_and_date')



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
            t.render(dict(
                items=self,
                document=self,
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
        return self._get_report_lines('l10n_fi_reports.account_financial_report_l10n_fi_pl')

    def py3o_bs_lines(self):
        return self._get_report_lines('l10n_fi_reports.account_financial_report_l10n_fi_bs')

    def _get_report_lines(self, report_xmlid):
        self.ensure_one()

        report = self.env.ref(report_xmlid)
        options = {'date': {}}
        options['date']['filter'] = 'custom'
        options['date']['date_from'] = self.date_from
        options['date']['date_to'] = self.date_to
        options['date']['mode'] = 'range'
        options['date']['period_type'] = 'fiscalyear'
        options['comparison'] = {'filter': 'same_last_year', 'number_period': 1}
        options['selected_analytic_account_names'] = []
        options['selected_analytic_tag_names'] = []
        options['unfold_all'] = False
        options['export_mode'] = 'file'
        options['all_entries'] = False # Do not include unposted entries, 14.0
        options['multi_company'] = [{
            'id': self.company_id.id,
            'name': self.company_id.name,
            'selected': True,
        }]
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




