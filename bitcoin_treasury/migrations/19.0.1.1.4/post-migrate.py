from bitwalkit import ExtendedKey
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    keys = env['bitcoin.key'].with_context(active_test=False).search([])
    for key in keys:
        if not key.xpub:
            continue
        parsed = ExtendedKey.parse(key.xpub.strip())
        vals = {
            'xpub': parsed.to_xpub(),
            'zpub': parsed.to_zpub(),
            'Zpub': parsed.to_Zpub(),
        }
        if (
            key.xpub != vals['xpub']
            or key.zpub != vals['zpub']
            or key.Zpub != vals['Zpub']
        ):
            key.write(vals)
