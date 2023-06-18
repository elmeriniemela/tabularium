# -*- coding: utf-8 -*-

import requests
import dateutil

from odoo import models, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)

class Currency(models.Model):
    _inherit = 'res.currency'

    def cron_update_rate(self, modes=['realtime', 'intraday', 'daily']):
        Rate = self.env['res.currency.rate']
        Asset = self.env['investment.asset']
        currencies = {c.name: c for c in self.search([])}
        from_currency = self.env.company.currency_id.name
        api_key = self.env['ir.config_parameter'].sudo().get_param('alpha.vantage.api.key')
        for to_currency, currency_id in currencies.items():
            rates = {}
            for mode in modes:
                try:
                    if mode == 'realtime':
                        resp = requests.get(f'https://www.alphavantage.co/query?function=CURRENCY_EXCHANGE_RATE&from_currency={from_currency}&to_currency={to_currency}&apikey={api_key}')
                        json_data = resp.json()
                        key = "Realtime Currency Exchange Rate"
                        if key not in json_data:
                            # Requires premium
                            raise ValidationError(str(json_data))
                        vals = json_data[key]
                        rates = {dateutil.parser.parse(vals['6. Last Refreshed']).date(): float(vals['5. Exchange Rate'])}
                    elif mode == 'intraday':
                        resp = requests.get(f'https://www.alphavantage.co/query?function=FX_INTRADAY&from_symbol={from_currency}&to_symbol={to_currency}&interval=5min&apikey={api_key}')
                        vals = resp.json()["Time Series FX (5min)"]
                        rates = {}
                        for d_str, w in vals.items():
                            date = dateutil.parser.parse(d_str).date()
                            if date not in rates:
                                rates[date] = float(w['4. close'])
                    elif mode == 'daily':
                        resp = requests.get(f'https://www.alphavantage.co/query?function=FX_DAILY&from_symbol={from_currency}&to_symbol={to_currency}&apikey={api_key}')
                        vals = resp.json()["Time Series FX (Daily)"]
                        rates = {dateutil.parser.parse(d_str).date(): float(w['4. close']) for d_str, w in vals.items() }
                    elif mode == 'weekly':
                        resp = requests.get(f'https://www.alphavantage.co/query?function=FX_WEEKLY&from_symbol={from_currency}&to_symbol={to_currency}&apikey={api_key}')
                        vals = resp.json()["Time Series FX (Weekly)"]
                        rates = {dateutil.parser.parse(d_str).date(): float(w['4. close']) for d_str, w in vals.items() }
                    else:
                        raise ValidationError(f"Invalid {mode=}")
                except Exception as error:
                    _logger.exception(error)
                else:
                    break

            if rates:
                _logger.info(f"Update {mode} rates on {to_currency}")
                for date, rate in rates.items():
                    rate_record = Rate.search([
                        ('currency_id', '=', currency_id.id),
                        ('name', '=', date),
                    ])
                    if rate_record:
                        rate_record.rate = rate
                    else:
                        Rate.create({
                            'name': date,
                            'currency_id': currency_id.id,
                            'rate': rate,
                        })

            Asset.search([('currency_id', '=', currency_id.id)])._compute_aggregate()



