# -*- coding: utf-8 -*-
{
    'name': "Account Financials",
    'author': "Elmeri Niemelä",
    'website': "https://eniemela.fi",
    'license': 'LGPL-3',
    'category': 'Accounting',
    'version': '0.1.2',
    'depends': [
        'account_accountant',
        'accountant',
        'l10n_fi_reports',
    ],
    'installable': True,
    'application': True,
    'data': [
        'views/account_fiscal_year.xml',
    ],
}
