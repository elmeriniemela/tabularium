# -*- coding: utf-8 -*-
{
    'name': 'Notes',
    'version': '1.3',
    'author': "Elmeri Niemelä",
    'category': 'Productivity/Notes',
    'summary': 'Organize your work with memos',
    'sequence': 260,
    'depends': [
        'mail',
    ],
    'data': [
        'security/note_security.xml',
        'security/ir.model.access.csv',
        'views/note_views.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
