{
    'name': 'Flight Log portal',
    'version': '1.0.2',
    'category': 'Uncategorized',
    'license': 'LGPL-3',
    'author': 'Elmeri Niemelä',
    'description': "Flight Log portal.",
    'depends': [
        'flight_log',
        'portal',
    ],
    'data': [
        'templates/start.xml',
        'views/flight_log.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
