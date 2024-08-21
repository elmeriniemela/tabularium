{
    'name': 'Cloud Manager Website',
    'version': '1.0',
    'category': 'Uncategorized',
    'license': 'LGPL-3',
    'author': 'Elmeri Niemelä',
    'description': "Cloud manager website.",
    'depends': [
        'cloud_manager',
        'website',
    ],
    'data': [
        'templates/start.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
