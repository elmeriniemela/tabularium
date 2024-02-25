
from odoo import api, SUPERUSER_ID

def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    activities = env['mail.activity'].search([('res_model_id', '=', env.ref('investment_portfolio.model_investment_asset').id)])
    activities.write({'res_model_id': env.ref('investment_portfolio.model_investment_position').id})