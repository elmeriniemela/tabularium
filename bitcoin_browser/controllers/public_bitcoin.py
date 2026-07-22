# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request


class BitcoinTxController(http.Controller):

    @http.route('/bitcoin/tx/<txid>', type='http', auth='public')
    def visualized_script(self, txid):
        tx = request.env['bitcoin.tx'].sudo().search_fetch(
            [('txid', '=', txid)], ['visualized_script'])
        if not tx:
            return request.not_found()
        return request.render('bitcoin_browser.tx_visualized_script', {'tx': tx})
