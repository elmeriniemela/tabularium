
import logging


from odoo import http, exceptions
from odoo.http import request


_logger = logging.getLogger(__name__)


class ApiController(http.Controller):

    @http.route('/api-endpoint/v1/<location>', type='http', auth="public", csrf=False)
    def api_endopoint(self, location, **params):
        return self._process(location, **params)

    def _process(self, location, **params):
        method = request.httprequest.method.lower()
        auth = request.httprequest.headers.get('Authorization') or ''
        data = request.httprequest.data
        _logger.info(f"{method=}, {location=} {auth=}, {params=}, {data=}")
        params['data'] = data
        return request.env['api.endpoint'].process_inbound_http(method, location, auth, params)
