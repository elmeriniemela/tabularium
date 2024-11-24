# -*- coding: utf-8 -*-

from odoo import models, fields, _


class InvestmentAssetSplit(models.Model):
    _name = 'investment.asset.split'
    _description = 'Investment Asset Split'
    _order = 'time, id'

    price_id = fields.Many2one(
        string="First price post split",
        comodel_name='investment.asset.price',
        index=True,
        required=True,
        domain="[('asset_id', '=', asset_id), ('prediction', '=', False)]",
    )

    asset_id = fields.Many2one(related='price_id.asset_id', store=True)

    time = fields.Datetime(related='price_id.time', store=True)

    factor = fields.Float(
        required=True,
    )

