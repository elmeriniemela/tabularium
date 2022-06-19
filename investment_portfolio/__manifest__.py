# -*- coding: utf-8 -*-
{
    'name': "Investment Portfolio",
    'author': "Elmeri Niemelä",
    'website': "https://eniemala.fi",
    'category': 'Uncategorized',
    'version': '0.1',
    'depends': [
        'base',
    ],
    'installable': True,
    'application': True,
    'data': [
        'security/ir.model.access.csv',
        'data/decimal.xml',
        'views/investment_asset.xml',
        'views/investment_category.xml',
        'views/investment_asset_price.xml',
        'views/investment_asset_transaction.xml',
    ],
}
