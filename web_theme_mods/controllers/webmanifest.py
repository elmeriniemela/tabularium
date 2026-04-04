from odoo.addons.web.controllers import webmanifest


class WebManifest(webmanifest.WebManifest):
    "Overwrite _get_webmanifest"

    def _get_webmanifest(self):
        manifest = super()._get_webmanifest()
        icon_sizes = ['192x192', '512x512']
        manifest['icons'] = [{
            'src': '/web_theme_mods/static/img/odoo-icon-%s.png' % size,
            'sizes': size,
            'type': 'image/png',
        } for size in icon_sizes]
        return manifest


