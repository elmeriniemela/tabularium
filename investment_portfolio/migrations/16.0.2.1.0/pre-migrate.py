
from odoo import api, SUPERUSER_ID

def migrate(cr, version):
    cr.execute("ALTER TABLE investment_asset_transaction RENAME TO investment_position_transaction")
    cr.execute("ALTER TABLE investment_asset_transaction_investment_timeseries_rel RENAME TO investment_position_transaction_investment_timeseries_rel")
    cr.execute("ALTER TABLE investment_position_transaction_investment_timeseries_rel RENAME COLUMN investment_asset_transaction_id TO investment_position_transaction_id")
    cr.execute("UPDATE ir_model SET model='investment.position.transaction' WHERE model='investment.asset.transaction'")
    env = api.Environment(cr, SUPERUSER_ID, {})

    for xmlid in env['ir.model.data'].search([('name', 'ilike', 'investment_asset_transaction')]):
        xmlid.name = xmlid.name.replace('investment_asset_transaction', 'investment_position_transaction')

