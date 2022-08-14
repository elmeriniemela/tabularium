# -*- coding: utf-8 -*-
{
    'name': "Cash Flow Management",
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
        'data/parser.xml',

        'views/cashflow_entry.xml',
        'views/cashflow_category.xml',
        'views/cashflow_parser.xml',
    ],
}
