# -*- coding: utf-8 -*-

from odoo import api, models, fields, _
from dateutil.relativedelta import relativedelta


class InvestmentAssetPrice(models.Model):
    _name = 'investment.asset.price'
    _description = 'Asset Price'
    _order = 'time desc'
    _rec_name = 'display_name'


    asset_id = fields.Many2one(
        comodel_name='investment.asset',
        required=True,
        ondelete='cascade',
        index=True,
    )
    currency_id = fields.Many2one(related='asset_id.currency_id')

    price = fields.Monetary(required=True, group_operator='avg', index=True)
    price_adjusted = fields.Monetary(group_operator='avg', compute='_compute_price_adjusted')


    time = fields.Datetime(required=True, default=fields.Datetime.now, index=True)

    prediction = fields.Boolean(index=True)

    interpolated = fields.Boolean(index=True)

    transaction_id = fields.Many2one(
        comodel_name='investment.position.transaction',
        index=True,
    )

    display_name = fields.Char(compute='_compute_display_name', store=True)

    _sql_constraints = [
        ('unique_price', 'unique(asset_id, time)', 'Price for this time is already configured!'),
    ]

    @api.depends('price', 'time')
    def _compute_display_name(self):
        for record in self:
            record.display_name = f'{record.price} @ {record.time}'

    @api.depends('asset_id.split_ids', 'asset_id.split_ids.factor')
    def _compute_price_adjusted(self):
        for rec in self:
            splits = rec.asset_id.split_ids
            adjusted = rec.price
            for s in splits.filtered(lambda s: rec.time < s.time):
                adjusted /=  s.factor
            rec.price_adjusted = adjusted


    def interpolate_cagr(self):
        assert len(self) == 2, "Two prices required"
        Price = self.env['investment.asset.price']
        first, last = self.sorted('time')
        n = (last.time-first.time).days/365
        cagr = ((last.price/first.price)**(1/n) - 1)

        time = first.time
        price = first.price
        while time < (last.time - relativedelta(months=1)):
            time += relativedelta(months=1)
            price *= (1+cagr)**(1/12)
            base_vals = {
                'interpolated': True,
                'asset_id': first.asset_id.id,
                'time': time,
            }
            price_id = Price.search([(key, '=', value) for key, value in base_vals.items()])
            if not price_id:
                price_id = Price.create({**base_vals, **{'price': price}})
            else:
                price_id.price = price




