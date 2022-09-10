# -*- coding: utf-8 -*-
{
    'name': "Timeago Widget",
    'author': "Elmeri Niemelä",
    'website': "https://eniemela.fi",
    'license': 'LGPL-3',
    'category': 'Uncategorized',
    'version': '0.1',
    'depends': [
        'web',
    ],
    'installable': True,
    'application': False,
    'data': [
    ],
    'assets': {
        'web.assets_backend': [
            '/timeago_widget/static/src/js/widget.js',
            '/timeago_widget/static/src/css/widget.css',
        ],
        "web.assets_qweb": [
            "/timeago_widget/static/src/xml/widget.xml",
        ],
        'web._assets_common_scripts': [
            'timeago_widget/static/src/lib/jquery.timeago.js',
        ]
    }
}
