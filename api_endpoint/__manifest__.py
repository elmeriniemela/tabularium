# -*- coding: utf-8 -*-
{
    'name': "API endpoint",
    'summary': "Build robust integrations with Odoo",
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
        'views/api_endpoint.xml',
        'views/api_message.xml',
        'data/cron.xml',
    ],
}
