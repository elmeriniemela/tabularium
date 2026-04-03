# -*- coding: utf-8 -*-

from collections import defaultdict
import logging
import datetime

from odoo import models, _
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT, DEFAULT_SERVER_DATETIME_FORMAT
from lxml import etree

_logger = logging.getLogger(__name__)

class Base(models.AbstractModel):
    _inherit = 'base'


    def ensure_xmlid(self, idformat=lambda record: f'{record._table}_{record.id}', module='__export__'):
        """
        Helper to generate XML-ID for export. Used in API endpoints.
        """
        Model = self.env['ir.model.data'].sudo()

        xmlid_map = {}
        for record in self:
            xmlid = idformat(record)
            modeldata = Model.search([
                ('model', '=', record._name),
                ('res_id', '=', record.id),
            ], order='id asc', limit=1)
            if not modeldata:
                modeldata = Model.create({
                    'name': xmlid,
                    'module': module,
                    'model': record._name,
                    'res_id': record.id,
                })
            xmlid_map[record] = modeldata.complete_name
        return xmlid_map


    def xml_export(self, field_names):
        root = etree.Element('odoo')
        self._xml_recursive_export(field_names, root)
        return root

    def _xml_recursive_export(self, field_names, root):
        basic_fields = []
        one2many_fields = defaultdict(list)
        for f in field_names:
            fbase = f.split('/')[0].lstrip('.')
            if '/' not in f.rstrip('/id'):
                basic_fields.append(fbase)
                continue

            if self._fields[fbase].type == 'one2many':
                one2many_fields[fbase].append(f[len(fbase)+1:])
                continue

            _logger.warning("Unable to export %s on %s", f, self._name)

        xmlid_map = self.ensure_xmlid()
        for r in self:
            xmlid = xmlid_map[r]
            record = etree.Element('record')
            record.set('id', xmlid)
            record.set('model', r._name)
            root.append(record)

            for f in basic_fields:
                field = etree.Element('field')
                field.set('name', f)
                r._xml_basic_field_export(f, field)
                record.append(field)

            for f, field_names in one2many_fields.items():
                field = etree.Element('field')
                field.set('name', f)
                val = r[f]
                val._xml_recursive_export(field_names, field)
                record.append(field)

    def _xml_basic_field_export(self, fname, field):
        self.ensure_one()
        val = self[fname]
        if isinstance(val, str):
            if val.strip().startswith('<'):
                try:
                    xmlval = etree.XML(val)
                except etree.XMLSyntaxError:
                    try:
                        xmlval = etree.HTML(val)
                    except etree.XMLSyntaxError: # pragma: no cover
                        field.text = val
                    else:
                        field.set('type', 'html')
                        field.append(xmlval)
                else:
                    field.set('type', 'xml')
                    field.append(xmlval)

            else:
                field.text = val

        elif isinstance(val, (int, float, bool)):
            field.set('eval', repr(val or False))
        elif isinstance(val, datetime.datetime):
            field.text = val.strftime(DEFAULT_SERVER_DATETIME_FORMAT)
        elif isinstance(val, datetime.date):
            field.text = val.strftime(DEFAULT_SERVER_DATE_FORMAT)

        elif isinstance(val, models.BaseModel):
            if val:
                val.ensure_one() # TODO: Many2many
                field.set('ref', str(val.ensure_xmlid()[val])) # TODO: Optimize the amount of calls?
            else:
                field.set('eval', repr(False))

