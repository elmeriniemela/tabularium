
import logging
import json

from werkzeug.exceptions import InternalServerError

from odoo import http, exceptions
from odoo.http import request


_logger = logging.getLogger(__name__)


class ApiController(http.Controller):

    @http.route('/api-endpoint/v1/<location>', type='http', auth="public", csrf=False)
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
            raise InternalServerError(
                description=msg,
                response=http.Response(
                    response=json.dumps({'error': msg}),
                    content_type='application/json',
                    status=500,
                )
            )