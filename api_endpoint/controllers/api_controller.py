
import logging
import json
from lxml import etree

from werkzeug.exceptions import InternalServerError
from werkzeug.routing import BaseConverter

from odoo import http, models
from odoo.http import request


_logger = logging.getLogger(__name__)


class WildcardConverter(BaseConverter):
    regex = r'(.*?)'
    weight = 200


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _get_converters(cls):
        """ Get the converters list for custom url pattern werkzeug need to
            match Rule. This override adds the website ones.
        """
        return dict(
            super(IrHttp, cls)._get_converters(),
            wildcard=WildcardConverter,
        )

class ApiController(http.Controller):

    @http.route('/api-endpoint/v1/<wildcard:location>', type='http', auth="public", csrf=False)
    def api_endopoint(self, location, **variables):
        return self._process(location, **variables)

    def _process(self, location, **variables):
        method = request.httprequest.method.lower()
        auth = request.httprequest.headers.get('Authorization') or ''
        data = request.httprequest.data
        _logger.info(f"{method=}, {location=} {auth=}, {variables=}, {data=}")
        variables['data'] = data
        try:
            return request.env['api.endpoint'].process_inbound_http(method, location, auth, variables)
        except Exception as exc:
            args = ', '.join(str(a) for a in exc.args)
            msg = f"{type(exc).__name__}: {args}"
            _logger.error(msg)

            content_type = request.httprequest.headers.get('Content-Type')
            if content_type == 'text/xml':
                elem = etree.Element('error')
                elem.text = msg
                resp_bytes = etree.tostring(elem, encoding='utf-8', xml_declaration=True)
            else:
                resp_bytes = json.dumps({'error': msg})
                content_type = 'application/json' # This is the default if a non supported content type is asked for.

            raise InternalServerError(
                description=msg,
                response=http.Response(
                    response=resp_bytes,
                    content_type=content_type,
                    status=500,
                )
            )