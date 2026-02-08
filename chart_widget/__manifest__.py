# -*- coding: utf-8 -*-
{
    'name': "Chart Widget",
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
            'chart_widget/static/src/xml/widget.xml',
            'chart_widget/static/src/js/widget.js',
            'chart_widget/static/src/css/widget.css',
        ],
        "chart_widget.lightweight_charts": [
            'chart_widget/static/src/lib/*.js',
        ]
    }
}
