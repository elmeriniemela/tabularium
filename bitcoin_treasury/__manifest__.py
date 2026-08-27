# -*- coding: utf-8 -*-
{
    'name': "Bitcoin Treasury",
    'summary': "Monitor watch-only Bitcoin wallets from extended public keys",
    'author': "Elmeri Niemelä",
    'website': "https://eniemela.fi",
    'license': 'LGPL-3',
    'category': 'Uncategorized',
    'version': '1.0.9',
    'depends': [
        'mail',
        'bitcoin_explorer',
    ],
    'external_dependencies': {'python': ['bitwalkit']},
    'installable': True,
    'application': True,
    'data': [
        'security/ir.model.access.csv',

        'views/bitcoin_tx.xml',
        'views/bitcoin_key.xml',
        'views/bitcoin_wallet.xml',
        'views/bitcoin_wallet_address.xml',
        'views/bitcoin_tx_out.xml',
        'views/bitcoin_tx_in.xml',

        'views/menuitems.xml',
    ],
}
