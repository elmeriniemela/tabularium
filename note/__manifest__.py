# -*- coding: utf-8 -*-
{
    'name': 'Notes',
    'version': '1.0',
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
        'data/mail_activity_type_data.xml',
        'data/note_data.xml',
        'views/note_views.xml',
        ],
    'demo': [
        'data/note_demo.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
