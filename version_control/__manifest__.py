# -*- coding: utf-8 -*-
{
    'name': "Version Control",
    'summary': "Manage versions of text fields",
    'author': "Elmeri Niemelä",
    'website': "https://eniemela.fi",
    'license': 'LGPL-3',
    'category': 'Uncategorized',
    'version': '1.0.2',
    'depends': [
        'base', 'mail',
    ],
    'installable': True,
    'application': True,
    'data': [
        'security/ir.model.access.csv',
        'views/version_control.xml',
    ],
}
