
from odoo import api, SUPERUSER_ID, Command

def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    followers = env['mail.followers'].search([])
    followers.write({'subtype_ids': [Command.link(env.ref('api_endpoint.mt_integration_error').id)],})
