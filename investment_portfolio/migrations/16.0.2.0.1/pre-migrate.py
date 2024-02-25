
from odoo import api, SUPERUSER_ID

def migrate(cr, version):
    cr.execute("DELETE FROM investment_timeseries WHERE price_id is NULL")
    cr.execute("ALTER TABLE investment_timeseries RENAME COLUMN last_price TO last_price_own_currency")

