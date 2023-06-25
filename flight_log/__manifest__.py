# -*- coding: utf-8 -*-
{
    'name': "Flight Log",
    'summary': "Sync flight time entries with Odoo",
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
        'views/flight_log.xml',
        'views/flight_plane.xml',
        'views/flight_airport.xml',
    ],
}
