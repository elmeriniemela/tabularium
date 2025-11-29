
from odoo import api, SUPERUSER_ID, Command

def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    cr.execute("SELECT id, cron_frequency FROM api_endpoint WHERE cron_frequency IS NOT NULL")
    for (id, cron_frequency) in cr.fetchall():
        env['api.endpoint'].browse(id).cron_id = env.ref('api_endpoint.cron_run_%s' % cron_frequency)

