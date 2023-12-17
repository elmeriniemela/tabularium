# -*- coding: utf-8 -*-
{
    'name': "Cloud Manager",
    'summary': "Manage your cloud infrastructre with Odoo",
    'author': "Elmeri Niemelä",
    'website': "https://eniemela.fi",
    'license': 'LGPL-3',
    'category': 'Uncategorized',
    'version': '1.0',
    'depends': [
        'base',
        'mail',
        'api_endpoint',
    ],
    'installable': True,
    'application': True,
    'data': [
        'security/ir.model.access.csv',
        'views/cloud_instance.xml',
        'views/cloud_backup.xml',
        'views/dns_zone.xml',
        'views/cloud_restore.xml',
        'views/menuitems.xml',

        'data/subtypes.xml',
    ],
}
