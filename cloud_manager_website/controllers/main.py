# -*- coding: utf-8 -*-
import logging

from odoo import http, tools, _
from odoo.http import request


_logger = logging.getLogger(__name__)


class WebsiteBackend(http.Controller):

    @http.route('/start', type='http', auth="public", website=True, methods=['GET', 'POST'])
    def start(self, **params):
        if request.httprequest.method == 'POST':
            print(params)
            return request.render("cloud_manager_website.start")
        else:
            return request.render("cloud_manager_website.start")

