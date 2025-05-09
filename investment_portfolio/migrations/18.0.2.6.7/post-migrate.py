
from odoo import api, SUPERUSER_ID

def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})

    positions = env['investment.position'].search([
        ('thesis_id', '=', False),
        ('thesis', '!=', False),
    ])
    for position in positions:
        position.thesis_id = env['investment.position.note'].create({
            'sequence': position.sequence,
            'name': position.name,
            'content': position.thesis,
            'company_id': position.company_id.id,
        })


