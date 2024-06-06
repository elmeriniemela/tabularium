
from odoo import api, SUPERUSER_ID

def migrate(cr, version):
    cr.execute("UPDATE flight_log SET purpose_id=(select id from flight_purpose WHERE code=purpose)")
