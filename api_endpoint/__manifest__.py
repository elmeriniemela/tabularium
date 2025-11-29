# -*- coding: utf-8 -*-
{
    'name': "API Framework",
    'summary': "Build robust integrations with Odoo",
    'author': "Elmeri Niemelä",
    'website': "https://eniemela.fi",
    'license': 'LGPL-3',
    'category': 'Uncategorized',
    'version': '1.0.9',
    'depends': [
        'base', 'mail',
        'version_control',
    ],
    'installable': True,
    'application': True,
    'data': [
        'security/ir.model.access.csv',
        'views/api_message.xml',
        'views/api_endpoint.xml',
        'views/menuitems.xml',
        'data/cron.xml',
        'data/subtypes.xml',
    ],
}
