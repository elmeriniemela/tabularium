# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request


class BitcoinTxController(http.Controller):

    @http.route('/bitcoin/tx/<txid>', type='http', auth='public')
    def visualized_script(self, txid):
        tx = request.env['bitcoin.tx'].sudo().search([('txid', '=', txid)])
        if not tx: # pragma: no cover
            return request.not_found()
        if not tx.is_visualized:
            tx.with_context(force_tx_refresh=True).refresh()
        return request.render('bitcoin_browser.tx_visualized_script', {'tx': tx})
