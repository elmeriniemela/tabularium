from odoo.addons.web.controllers import webmanifest


class WebManifest(webmanifest.WebManifest):

    def _get_webmanifest(self):
        manifest = super()._get_webmanifest()
        manifest['icons'] = [{
            'src': '/web_theme_mods/static/description/icon.png',
            'sizes': 'any',
            'type': 'image/png',
        }]
        return manifest


