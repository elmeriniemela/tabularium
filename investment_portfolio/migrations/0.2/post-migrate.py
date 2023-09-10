
from odoo import api, SUPERUSER_ID

def migrate(cr, version):
    cr.execute("UPDATE investment_asset_transaction SET usage='prediction' WHERE prediction=True")
