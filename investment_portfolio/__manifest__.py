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
        'timeago_widget',
    ],
    'installable': True,
    'application': True,
    'data': [
        'security/ir.model.access.csv',
        'data/decimal.xml',
        'data/ir_cron_data.xml',
        'views/investment_asset.xml',
        'views/investment_timeseries.xml',
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
