# -*- coding: utf-8 -*-
import logging
import binascii

from odoo import http, models, tools, _
from odoo.http import request
from odoo.exceptions import AccessError, MissingError, ValidationError
from odoo.addons.portal.controllers import portal


_logger = logging.getLogger(__name__)

class ReslogAccessUrl(models.Model):
    _name = "flight.log"
    _inherit = ['flight.log', 'portal.mixin']

    def _compute_access_url(self):
        super()._compute_access_url()
        for log in self:
            log.access_url = '/flight/log/%s' % (log.id)

    def _get_portal_return_action(self):
        """ Return the action used to display orders when returning from customer portal. """
        self.ensure_one()
        return self.env.ref('flight_log.log_action')

    def action_preview_flight_log(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'target': 'self',
            'url': self.get_portal_url(),
        }


class FlightLog(portal.CustomerPortal):

    @http.route(['/flight/log/<int:log_id>'], type='http', auth="public", website=True)
    def flight_log_page(self, log_id, access_token=None, message=False, download=False, **kw):
        try:
            log_sudo = self._document_check_access('flight.log', log_id, access_token=access_token)
        except (AccessError, MissingError):
            return request.redirect('/my')


        backend_url = f'/web#model={log_sudo._name}'\
                      f'&id={log_sudo.id}'\
                      f'&action={log_sudo._get_portal_return_action().id}'\
                      f'&view_type=form'
        values = {
            'flight_log': log_sudo,
            'message': message,
            'report_type': 'html',
            'backend_url': backend_url,
            'res_company': log_sudo.company_id,  # Used to display correct company logo
        }

        values = self._get_page_view_values(
            log_sudo, access_token, values, 'flight_log', False)

        return request.render('flight_log_portal.flight_log_portal_template', values)

    @http.route(['/flight/log/<int:log_id>/accept'], type='jsonrpc', auth="public", website=True)
    def flight_log_accept(self, log_id, access_token=None, name=None, signature=None):
        # get from query string if not on json param
        access_token = access_token or request.httprequest.args.get('access_token')
        try:
            log_sudo = self._document_check_access('flight.log', log_id, access_token=access_token)
        except (AccessError, MissingError):
            return {'error': _('Invalid flight log.')}

        if not signature:
            return {'error': _('Signature is missing.')}

        try:
            log_sudo.write({
                'signatory_license_number': name,
                'sign': signature,
                'state': 'confirmed',
            })
            request.env.cr.commit()

        except (TypeError, binascii.Error) as e:
            return {'error': _('Invalid signature data.')}


        query_string = '&message=sign_ok'
        return {
            'force_refresh': True,
            'redirect_url': log_sudo.get_portal_url(query_string=query_string),
        }
