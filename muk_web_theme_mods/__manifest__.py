{
    'name': 'MuK Backend Theme MODS',
    'version': '16.0.1.0.6',
    'category': 'Themes/Backend',
    'license': 'LGPL-3',
    'author': 'Elmeri Niemelä',
    'description': "Fix One2many list view footer color so that numbers are visible",
    'depends': [
        'muk_web_theme',
    ],
    'assets': {
        'web._assets_backend_helpers': [
            (
                'after',
                'muk_web_theme/static/src/variables.scss',
                'muk_web_theme_mods/static/src/variables.scss'
            ),
        ],
        'web.assets_backend': [
            (
                'after',
                'muk_web_theme/static/src/views/list/list.scss',
                'muk_web_theme_mods/static/src/views/list/list.scss'
            ),
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
