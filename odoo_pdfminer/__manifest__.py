# -*- coding: utf-8 -*-
{
    'name': "Odoo PDF Miner",
    'author': "Elmeri Niemelä",
    'website': "www.thecodebase.tech",
    'category': 'Uncategorized',
    'version': '0.1',
    'depends': [
        'base',
        'account',
    ],
    "external_dependencies": {"python": ["pdfminer.six"]},
    'data': [
        'security/ir.model.access.csv',
        'wizards/account_import_pdfminer_view.xml',
        'views/odoo_pdf_miner_views.xml',

        'data/pdfminer.xml',
    ],
}
