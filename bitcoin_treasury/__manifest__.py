# -*- coding: utf-8 -*-
{
    'name': "Bitcoin Treasury",
    'author': "Elmeri Niemelä",
    'website': "https://eniemela.fi",
    'license': 'LGPL-3',
    'category': 'Uncategorized',
    'version': '0.1.1',
    'depends': [
        'mail',
        'bitcoin_browser',
    ],
    'installable': True,
    'application': True,
    'data': [
        'security/ir.model.access.csv',

        'views/bitcoin_tx.xml',
        'views/bitcoin_key.xml',
        'views/bitcoin_wallet.xml',

        'views/menuitems.xml',
    ],
}
