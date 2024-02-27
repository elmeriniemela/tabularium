# -*- coding: utf-8 -*-
{
    'name': "Bitcoin Investment Sync",
    'author': "Elmeri Niemelä",
    'website': "https://eniemela.fi",
    'license': 'LGPL-3',
    'category': 'Uncategorized',
    'version': '0.1.3',
    'depends': [
        'investment_portfolio',
        'bitcoin_browser',
    ],
    'installable': True,
    'auto_install': True,
    'application': False,
    'data': [
        'views/bitcoin_wallet.xml',
    ],
}
