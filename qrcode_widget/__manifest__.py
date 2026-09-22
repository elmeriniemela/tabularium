# -*- coding: utf-8 -*-
{
    'name': "QR Code Widget",
    'author': "Elmeri Niemelä",
    'website': "https://eniemela.fi",
    'license': 'LGPL-3',
    'category': 'Uncategorized',
    'version': '1.0',
    'depends': [
        'web',
    ],
    'installable': True,
    'application': False,
    'assets': {
        'web.assets_backend': [
            'qrcode_widget/static/src/qrcode_text/*',
        ],
        'web.assets_unit_tests': [
            'qrcode_widget/static/tests/**/*',
        ],
    },
}
