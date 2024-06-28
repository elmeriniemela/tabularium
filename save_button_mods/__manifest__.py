{
    'name': 'Save Button MODS',
    'version': '1.0',
    'category': 'Themes/Backend',
    'license': 'LGPL-3',
    'author': 'Elmeri Niemelä',
    'description': "Increase save/cancel button size and padding.",
    'depends': [
        'web',
    ],
    'assets': {
        'web._assets_primary_variables': [
            (
                'after',
                'web/static/src/scss/primary_variables.scss',
                'save_button_mods/static/src/views/save/save.scss'
            ),
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
