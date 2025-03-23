# -*- coding: utf-8 -*-
{
    'name': "Toggl Sync",
    'summary': "Sync Toggl time entries with Odoo",
    'author': "Elmeri Niemelä",
    'website': "https://eniemela.fi",
    'license': 'LGPL-3',
    'category': 'Toggl',
    'version': '1.0.3',
    'depends': [
        'base', 'mail',
        'timeago_widget',
    ],
    'installable': True,
    'application': True,
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'wizards/toggl_import.xml',
        'views/toggl_entry.xml',
        'views/toggl_task.xml',
        'views/res_users.xml',
    ],
}
