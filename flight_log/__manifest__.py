# -*- coding: utf-8 -*-
{
    'name': "Flight Log",
    'summary': "Sync flight time entries with Odoo",
    'author': "Elmeri Niemelä",
    'website': "https://eniemela.fi",
    'license': 'LGPL-3',
    'category': 'Flight Log',
    'version': '1.1.2',
    'depends': [
        'base', 'mail',
    ],
    'installable': True,
    'application': True,
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/flight_log.xml',
        'views/flight_plane.xml',
        'views/flight_airport.xml',
    ],
}
