# -*- coding: utf-8 -*-
{
    'name': 'Account Financials',
    'author': 'Elmeri Niemelä',
    'website': 'https://eniemela.fi',
    'license': 'LGPL-3',
    'category': 'Accounting',
    'version': '0.1.3',
    'depends': [
        'account',
    ],
    'installable': True,
    'application': True,
    'data': [
        'security/ir.model.access.csv',
        'views/account_fiscal_year.xml',
    ],
    'external_dependencies': {
        'python': ['py3o.template', 'py3o.formats'],
    },
}
