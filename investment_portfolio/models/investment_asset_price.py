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

    price = fields.Monetary(required=True, aggregator='avg', index=True)
    price_adjusted = fields.Monetary(aggregator='avg', compute='_compute_price_adjusted')


    time = fields.Datetime(required=True, default=fields.Datetime.now, index=True)
    date = fields.Date(compute='_compute_date')

    prediction = fields.Boolean(index=True)

    interpolated = fields.Boolean(index=True)

    transaction_id = fields.Many2one(
        comodel_name='investment.position.transaction',
        index=True,
    )

    display_name = fields.Char(compute='_compute_display_name', store=True)

    split_ids = fields.One2many(
        comodel_name='investment.asset.split',
        inverse_name='price_id',
        readonly=True,
    )

    timeseries_ids = fields.One2many(
        comodel_name='investment.timeseries',
        inverse_name='price_id',
        readonly=True,
    )

    asset_ids = fields.Many2many(
        string="Linked assets",
        comodel_name='investment.asset',
        compute='_compute_asset_ids',
        readonly=True,

    )

    _unique_price = models.Constraint('unique(asset_id, time)', 'Price for this time is already configured!')


    def action_view_assets(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Investment Asset'),
            'res_model': 'investment.asset',
            'view_mode': 'list',
            'views': [[False, 'list'], [False, 'form']],
            'domain': [('id', 'in', self.mapped('asset_ids').ids)],
        }

    def action_view_timeseries(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Investment Timeseries'),
            'res_model': 'investment.timeseries',
            'view_mode': 'list',
            'views': [[False, 'list'], [False, 'form']],
            'domain': [('id', 'in', self.mapped('timeseries_ids').ids)],
        }

    def action_view_splits(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Investment Split'),
            'res_model': 'investment.split',
            'view_mode': 'list',
            'views': [[False, 'list'], [False, 'form']],
            'domain': [('id', 'in', self.mapped('split_ids').ids)],
        }


    def _compute_asset_ids(self):
        Asset = self.env["investment.asset"].browse()
        price_field_maps = {}
        price_fields = [
            'last_price_id', 'daily_price_id', 'weekly_price_id', 'monthly_price_id', 'three_month_price_id',
            'six_month_price_id', 'ytd_price_id', 'one_year_price_id', 'three_year_price_id', 'five_year_price_id',
            'ten_year_price_id',
        ]
        for field in price_fields:
            price_field_maps[field] = dict(Asset._read_group(
                domain=[
                    (field, 'in', self.ids),
                ],
                groupby=[field],
                aggregates=["id:recordset"],
            ))


        for record in self:
            assert len(Asset) == 0
            assets = Asset.browse()
            for field in price_fields:
                assets += price_field_maps[field].get(record, Asset)
            record.asset_ids = assets


    def _compute_date(self):
        for record in self:
            record.date = record.time.date()

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




