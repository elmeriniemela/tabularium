
from odoo import api, SUPERUSER_ID

def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})


    CONSUME = env['investment.asset'].search([('ticker', '=', 'CONSUME')]) or env['investment.asset'].create({
        'ticker': 'CONSUME',
        'category_id': env['investment.category'].search([], limit=1).id,
        'currency_id': env.user.company_id.currency_id.id,
    })
    CONSUME.ensure_one()

    EUR = env['investment.asset'].search([('ticker', '=', 'EUR')])
    EUR.ensure_one()

    Pos = env['investment.position']

    for company in env['res.company'].search([]):
        company.cash_position_id = Pos.search([('asset_id', '=', EUR.id), ('company_id', '=', company.id)]) or Pos.create({
            'name': 'Cash',
            'asset_id': EUR.id,
            'company_id': company.id,
            'portfolio_id': 1,
            'follow': False,
        })

        company.consumption_position_id = Pos.search([('asset_id', '=', CONSUME.id), ('company_id', '=', company.id)]) or Pos.create({
            'name': 'Consumption',
            'asset_id': CONSUME.id,
            'company_id': company.id,
            'portfolio_id': 1,
            'follow': False,
        })


