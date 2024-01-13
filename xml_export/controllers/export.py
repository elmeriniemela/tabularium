
import json
import logging
import operator
from lxml import etree

from werkzeug.exceptions import InternalServerError

from odoo import http
from odoo.http import content_disposition, request
from odoo.exceptions import UserError
from odoo.tools import osutil
from odoo.tools.translate import _
from odoo.addons.web.controllers import export as stdexp


_logger = logging.getLogger(__name__)

class Export(stdexp.Export):

    @http.route('/web/export/formats', type='json', auth="user")
    def formats(self):
        return super().formats() + [
            {'tag': 'xml', 'label': 'XML'},
        ]

class XMLExport(stdexp.ExportFormat, http.Controller):

    @http.route('/web/export/xml', type='http', auth="user")
    def index(self, data):
        try:
            return self.xml_export(data)
        except Exception as exc:
            _logger.exception("Exception during request handling.")
            payload = json.dumps({
                'code': 200,
                'message': "Odoo Server Error",
                'data': http.serialize_exception(exc)
            })
            raise InternalServerError(payload) from exc

    @property
    def content_type(self):
        return 'text/xml;charset=utf8'

    @property
    def extension(self):
        return '.xml'

    def xml_export(self, data):
        "Adapted form self.base"
        params = json.loads(data)
        model, fields, ids, domain, import_compat = operator.itemgetter('model', 'fields', 'ids', 'domain', 'import_compat')(params)

        Model = request.env[model].with_context(import_compat=import_compat, **params.get('context', {}))
        if not Model._is_an_ordinary_table():
            fields = [field for field in fields if field['name'] != 'id']

        field_names = [f['name'] for f in fields]
        groupby = params.get('groupby')
        if not import_compat and groupby:
            raise UserError(_("Exporting grouped data to XML is not supported."))

        records = Model.browse(ids) if ids else Model.search(domain, offset=0, limit=False, order=False)
        root = records.xml_export(field_names)
        etree.indent(root, space="    ")
        response_data = etree.tostring(root, pretty_print=True, encoding='utf-8', xml_declaration=True)
        return request.make_response(response_data,
            headers=[('Content-Disposition',
                            content_disposition(
                                osutil.clean_filename(self.filename(model) + self.extension))),
                     ('Content-Type', self.content_type)],
        )