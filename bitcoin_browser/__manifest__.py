# -*- coding: utf-8 -*-
{
    'name': "Bitcoin Browser",
    'author': "Elmeri Niemelä",
    'website': "https://eniemela.fi",
    'license': 'LGPL-3',
    'category': 'Bitcoin',
    'version': '0.1.6',
    'depends': [
        'mail',
    ],
    'installable': True,
    'application': True,
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/decimal.xml',
        'data/cron.xml',
        'views/bitcoin_block.xml',
        'views/bitcoin_tx.xml',
        'templates/visualized_script.xml',
        'controllers/public_bitcoin.xml',
        'views/bitcoin_tx_in.xml',
        'views/bitcoin_tx_out.xml',
        'views/menuitems.xml',
    ],
}
