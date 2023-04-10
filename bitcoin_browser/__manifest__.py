# -*- coding: utf-8 -*-
{
    'name': "Bitcoin Browser",
    'author': "Elmeri Niemelä",
    'website': "https://eniemela.fi",
    'license': 'LGPL-3',
    'category': 'Uncategorized',
    'version': '0.1',
    'depends': [
        'mail',
    ],
    'installable': True,
    'application': True,
    'data': [
        'security/ir.model.access.csv',
        'data/decimal.xml',
        'data/cron.xml',
        'views/bitcoin_block.xml',
        'views/bitcoin_tx.xml',
        'views/bitcoin_tx_in.xml',
        'views/bitcoin_tx_out.xml',
        'views/menuitems.xml',
    ],
}
