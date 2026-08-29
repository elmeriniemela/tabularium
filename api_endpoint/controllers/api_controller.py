
import logging
import json
from lxml import etree

from werkzeug.exceptions import BadRequest, Forbidden, HTTPException, NotFound, RequestEntityTooLarge
from werkzeug.routing import BaseConverter

from odoo import http, models, exceptions
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
        _logger.info("API method=%s location=%s auth=%s variables=%s",
            method, location, 'set' if auth else 'empty', sorted(variables),
        )
        try:
            endpoint = self._match_to_endpoint(method, location, auth)
            if not endpoint.authorization:
                variables['data'] = self._read_request_data()
            else:
                variables['data'] = request.httprequest.data

            request_files = request.httprequest.files
            variables = {name: value for name, value in variables.items() if name not in request_files}
            if 'files' in variables:
                raise BadRequest("'files' is reserved for uploaded files.")
            variables['files'] = [{
                'name': name,
                'filename': file.filename,
                'content_type': file.content_type,
                'data': file.read(),
            } for name, file in request_files.items(multi=True)]
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


    def _read_request_data(self):
        max_bytes = int(request.env['ir.config_parameter'].sudo().get_param('api_endpoint.max_request_bytes', '1048576'))
        assert max_bytes > 0
        content_length = request.httprequest.content_length
        if content_length is not None and content_length > max_bytes:
            raise RequestEntityTooLarge()

        request.httprequest.max_content_length = max_bytes
        data = request.httprequest.get_data(cache=False)
        if len(data) > max_bytes:
            raise RequestEntityTooLarge()
        return data

    def _match_to_endpoint(self, method, location, auth):
        if method not in ['get', 'post', 'delete', 'put']:
            raise NotFound()

        Endpoint = request.env['api.endpoint'].sudo()
        domain = [
            ('role', '=', 'passive'),
            ('comm_method', '=', 'http'),
            ('http_method', 'in', [method, False]),
            ('location', '=', location),
            ('direction', '=', 'outbound' if method == 'get' else 'inbound'),
        ]
        endpoint = Endpoint.search(domain, limit=1)
        if endpoint.authorization and endpoint.authorization != auth:
            raise Forbidden()
        elif endpoint:
            return endpoint
        raise NotFound()

    def _raise_error(self, exc):
        args = ', '.join(str(a) for a in exc.args)
        _logger.error(f"{type(exc).__name__}: {args}")

        if isinstance(exc, HTTPException):
            status = exc.code
            msg = exc.name
            _logger.warning("API endpoint request rejected: %s", exc)
        elif isinstance(exc, exceptions.UserError):
            status = 400
            msg = f'Bad Request: {args}'
        else:
            status = 500
            msg = 'Internal Server Error'

        if request.httprequest.mimetype == 'text/xml':
            elem = etree.Element('error')
            elem.text = msg
            resp_bytes = etree.tostring(elem, encoding='utf-8', xml_declaration=True)
            content_type = 'text/xml'
        else:
            resp_bytes = json.dumps({'error': msg}).encode('utf-8')
            content_type = 'application/json' # This is the default if a non supported content type is asked for.

        return http.Response(
            response=resp_bytes,
            content_type=content_type,
            status=status,
        )
