# -*- coding: utf-8 -*-
{
    'name': "Investment Portfolio",
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
        'data/ir_cron_data.xml',
        'views/investment_asset.xml',
        'views/investment_position.xml',
        'views/investment_category.xml',
        'views/investment_integration.xml',
        'views/investment_asset_price.xml',
        'views/investment_asset_transaction.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'investment_portfolio/static/src/js/widget.js',
        ],
    }
}
