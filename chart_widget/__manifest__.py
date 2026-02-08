# -*- coding: utf-8 -*-
{
    'name': "Chart Widget",
    'author': "Elmeri Niemelä",
    'website': "https://eniemela.fi",
    'license': 'LGPL-3',
    'category': 'Uncategorized',
    'version': '0.2',
    'depends': [
        'web',
    ],
    'installable': True,
    'application': False,
    'data': [
    ],
    'assets': {
        'web.assets_backend': [
            'chart_widget/static/src/chart_arch_parser.js',
            'chart_widget/static/src/chart_model.js',
            'chart_widget/static/src/chart_renderer.js',
            'chart_widget/static/src/chart_renderer.xml',
            'chart_widget/static/src/chart_controller.js',
            'chart_widget/static/src/chart_controller.xml',
            'chart_widget/static/src/chart_view.js',
        ],
        "chart_widget.lightweight_charts": [
            'chart_widget/static/src/lib/*.js',
        ],
        'web.assets_unit_tests': [
            'chart_widget/static/tests/**/*',
        ],
    }
}
