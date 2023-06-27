# -*- coding: utf-8 -*-
{
    'name': "file scanner",
    'summary': "Sync file time entries with Odoo",
    'author': "Elmeri Niemelä",
    'website': "https://eniemela.fi",
    'license': 'LGPL-3',
    'category': 'Uncategorized',
    'version': '1.0',
    'depends': [
        'base', 'mail',
    ],
    'installable': True,
    'application': True,
    'data': [
        'security/ir.model.access.csv',
        'views/file_scanner.xml',
        'data/cron.xml',
    ],
}
