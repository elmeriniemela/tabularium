# -*- coding: utf-8 -*-
{
    'name': "Diff Widget",
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
            'diff_widget/static/src/lib/*.js',
            'diff_widget/static/src/lib/*.css',
            'diff_widget/static/src/xml/widget.xml',
            'diff_widget/static/src/js/widget.js',
            'diff_widget/static/src/css/widget.css',
        ],
    }
}
