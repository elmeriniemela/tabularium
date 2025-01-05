
from odoo import api, SUPERUSER_ID

def migrate(cr, version):
    """Migrate data from investment_asset_res_users_rel to investment_asset_res_company_rel. The company is taken from the user"""
    cr.execute("INSERT INTO investment_asset_res_company_rel (investment_asset_id, res_company_id) SELECT rel.investment_asset_id, u.company_id FROM investment_asset_res_users_rel rel LEFT JOIN res_users u ON rel.res_users_id = u.id")

