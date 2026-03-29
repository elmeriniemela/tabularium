# -*- coding: utf-8 -*-

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    investment_lock_time = fields.Datetime(
        help="Transactions/Realized asset entries before this date cannot be created, modified, or deleted.",
    )
