# -*- coding: utf-8 -*-

from odoo import api, exceptions, fields, models, Command, _


class BitcoinWallet(models.Model):
    _inherit = 'bitcoin.wallet'

    position_id = fields.Many2one(
        comodel_name='investment.position',
        index=True,
    )


    def show_investment_transactions(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Investment Transactions'),
            'res_model': 'investment.position.transaction',
            'view_mode': 'list',
            'views': [[False, 'list'], [False, 'form']],
            'domain': [('id', 'in', self.mapped('history_ids.position_transaction_id').ids)],
        }

    def refresh(self):
        super().refresh()
        self.sync_investments()


    def sync_investments(self):
        for wallet in self:
            if not wallet.position_id:
                continue

            for hist in wallet.history_ids:
                if hist.position_transaction_id:
                    continue

                price = hist.env['investment.asset.price'].search([
                    ('asset_id', '=', wallet.position_id.asset_id.id),
                    ('time', '<=', hist.date),
                ], order='time desc', limit=1)
                if price.time.date() != hist.date.date():
                    raise exceptions.UserError(_("Unable to find daily price for %s") % (hist.date))

                other_wallet_tx = hist.transaction_id.wallet_history_ids.position_transaction_id
                if other_wallet_tx:
                    hist.position_transaction_id = other_wallet_tx
                    qty = sum(hist.transaction_id.wallet_history_ids.mapped('amount'))
                    hist.position_transaction_id.write({
                        'quantity': qty,
                        'payment': 0,
                        'description': 'Transfer between wallets',
                    })
                else:
                    hist.position_transaction_id = hist.env['investment.position.transaction'].create({
                        'position_id': wallet.position_id.id,
                        'time': hist.date,
                        'payment': abs(hist.amount * price.price),
                        'quantity': hist.amount,
                        'exchange_rate': price.price,
                        'description': 'Automatically generated',
                    })



class BitcoinWalletHistory(models.Model):
    _inherit = 'bitcoin.wallet.history'


    position_transaction_id = fields.Many2one(
        comodel_name='investment.position.transaction',
        index=True,
    )