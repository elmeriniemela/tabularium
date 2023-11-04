
import logging


from odoo import http, exceptions
from odoo.http import request


_logger = logging.getLogger(__name__)


class ApiController(http.Controller):

    @http.route('/api-endpoint/v1/<location>', type='http', auth="none")
    def api_endopoint(self, location, **kw):
        method = request.httprequest.method.lower()
        auth = request.httprequest.headers.get('Authorization') or ''
        import pdb; pdb.set_trace()
        return 'OK'

