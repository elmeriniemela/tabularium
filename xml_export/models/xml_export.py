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

    def _xml_basic_field_export(self, fname, field):
        self.ensure_one()
        val = self[fname]
        if isinstance(val, str):
            if val.strip().startswith('<'):
                try:
                    xmlval = etree.XML(val)
                except etree.XMLSyntaxError:
                    field.text = val
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
            val.ensure_one() # TODO: Many2many
            if val:
                field.set('ref', str(val._get_xmlid_map()[val])) # TODO: Optimize the amount of calls?
            else:
                field.set('eval', repr(False))


    def _get_xmlid_map(self):
        return dict(self._BaseModel__ensure_xml_id())

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

        xmlid_map = self._get_xmlid_map()
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


    def xml_export(self, field_names):
        root = etree.Element('odoo')
        self._xml_recursive_export(field_names, root)
        return root
