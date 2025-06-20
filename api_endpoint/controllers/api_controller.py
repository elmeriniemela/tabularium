
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

    @http.route('/api-v1/<wildcard:location>', type='http', auth="public", csrf=False)
    def api_endopoint(self, location, **variables):
        return self._process(location, **variables)

    def _process(self, location, **variables):
        method = request.httprequest.method.lower()
        auth = request.httprequest.headers.get('Authorization') or variables.get('Authorization') or ''
        data = request.httprequest.data
        _logger.info(f"{method=}, {location=} {auth=}, {variables=}, {data=}")
        variables['data'] = data
        try:
            endpoint = self._match_to_endpoint(method, location, auth, variables)
        except Exception as exc:
            return self._raise_error(exc)

        try:
            globals_dict = endpoint.produce(variables)
            endpoint.ensure_response(globals_dict)
            response = globals_dict['response']
            bytesdata = endpoint.obj_to_bytes(response, endpoint.response_format)
        except Exception as exc:
            _logger.exception(exc)
            return self._raise_error(exc)



        if endpoint.response_format == 'xml':
            content_type = 'text/xml'
        elif endpoint.response_format == 'redirect':
            return request.redirect(**response)
        else: # TODO zip, csv, bytes
            content_type = 'application/json'

        return http.Response(
            response=bytesdata,
            content_type=content_type,
            status=200,
        )


    def _match_to_endpoint(self, method, location, auth, variables):
        assert method in ['get', 'post', 'delete', 'put']
        domain = [
            ('role', '=', 'passive'),
            ('comm_method', '=', 'http'),
            ('http_method', 'in', [method, False]),
            ('location', '=', location),
            ('authorization', 'in', [auth, False]),
            ('direction', '=', 'outbound' if method == 'get' else 'inbound'),
        ]
        endpoint = request.env['api.endpoint'].sudo().search(domain, limit=1)
        if not endpoint:
            raise RuntimeError(f"Endpoint not found: {domain}")
        return endpoint


    def _raise_error(self, exc):
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