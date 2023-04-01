# -*- coding: utf-8 -*-
{
    'name': "Document Directory",
    'author': "Elmeri Niemelä",
    'website': "https://eniemela.fi",
    'license': 'LGPL-3',
    'category': 'Uncategorized',
    'version': '0.1',
    'depends': [
        'mail',
    ],
    'installable': True,
    'application': False,
    'data': [
        'security/ir.model.access.csv',
        'views/document_directory.xml',
    ],
}
