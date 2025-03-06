# -*- coding: utf-8 -*-
{
    'name': "Document Directory",
    'author': "Elmeri Niemelä",
    'website': "https://eniemela.fi",
    'license': 'LGPL-3',
    'category': 'Documents',
    'version': '0.1.2',
    'depends': [
        'mail',
    ],
    'installable': True,
    'application': True,
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/document_directory.xml',
    ],
}
