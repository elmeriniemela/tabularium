
from odoo import api, SUPERUSER_ID

def migrate(cr, version):
    cr.execute("CREATE TABLE investment_position (LIKE investment_asset INCLUDING ALL)")
    cr.execute("INSERT INTO investment_position (SELECT * FROM investment_asset)")
    cr.execute("ALTER TABLE investment_position ADD COLUMN asset_id INTEGER")
    cr.execute("UPDATE investment_position SET asset_id=id")
    cr.execute("UPDATE investment_asset SET message_main_attachment_id=NULL")

    cr.execute("ALTER TABLE investment_asset_realized RENAME COLUMN asset_id TO position_id")
    cr.execute("ALTER TABLE investment_asset_realized DROP CONSTRAINT investment_asset_realized_asset_id_fkey")
    cr.execute("ALTER TABLE investment_asset_realized ADD CONSTRAINT investment_asset_realized_position_id_fkey FOREIGN KEY (position_id) REFERENCES investment_position(id) ON DELETE CASCADE")


    cr.execute("ALTER TABLE investment_asset_transaction RENAME COLUMN asset_id TO position_id")
    cr.execute("ALTER TABLE investment_asset_transaction DROP CONSTRAINT investment_asset_transaction_asset_id_fkey")
    cr.execute("ALTER TABLE investment_asset_transaction ADD CONSTRAINT investment_asset_transaction_position_id_fkey FOREIGN KEY (position_id) REFERENCES investment_position(id) ON DELETE CASCADE")


    cr.execute("ALTER TABLE investment_timeseries RENAME COLUMN asset_id TO position_id")
    cr.execute("ALTER TABLE investment_timeseries DROP CONSTRAINT investment_timeseries_asset_id_fkey")
    cr.execute("ALTER TABLE investment_timeseries ADD CONSTRAINT investment_timeseries_position_id_fkey FOREIGN KEY (position_id) REFERENCES investment_position(id) ON DELETE CASCADE")

    cr.execute("UPDATE ir_attachment SET res_model='investment.position' WHERE res_model='investment.asset'")
    cr.execute("UPDATE mail_message SET model='investment.position' WHERE model='investment.asset'")

