# -*- coding: utf-8 -*-
{
    'name': "Cash Flow Management",
    'author': "Elmeri Niemelä",
    'website': "https://eniemela.fi",
    'license': 'LGPL-3',
    'category': 'Cash Flow',
    'version': '1.0.3',
    'depends': [
        'mail',
    ],
    'installable': True,
    'application': True,
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/parser.xml',

        'views/cashflow_import.xml',
        'views/cashflow_entry.xml',
        'views/cashflow_plan.xml',
        'views/cashflow_category.xml',
        'views/cashflow_account.xml',
        'views/cashflow_parser.xml',
    ],
}
