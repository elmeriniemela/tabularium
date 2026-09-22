from odoo.tools.sql import column_exists, rename_column


def migrate(cr, version):
    if column_exists(cr, 'bitcoin_key', 'wif'):
        rename_column(cr, 'bitcoin_key', 'wif', 'xpub')
    if column_exists(cr, 'bitcoin_key', 'real_parent_fingerprint'):
        rename_column(cr, 'bitcoin_key', 'real_parent_fingerprint', 'master_fingerprint')
    if column_exists(cr, 'bitcoin_key', 'real_derivation_path'):
        rename_column(cr, 'bitcoin_key', 'real_derivation_path', 'derivation')
