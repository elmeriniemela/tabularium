# -*- coding: utf-8 -*-

from datetime import timedelta
from odoo import api, models, fields, Command, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)

class InvestmentPositionTransaction(models.Model):
    _name = 'investment.position.transaction'
    _description = 'Position Transaction'
    _inherit = ['mail.thread']
    _order = 'time desc, ttype'

    active = fields.Boolean(default=True, tracking=True)

    display_name = fields.Char(compute='_compute_display_name')

    position_id = fields.Many2one(
        comodel_name='investment.position',
        required=True,
        ondelete='cascade',
        index=True,
        tracking=True,
    )

    move_id = fields.Many2one(
        comodel_name='investment.position.move',
        ondelete='set null',
        index=True,
        tracking=True,
    )

    import_id = fields.Many2one(
        comodel_name='investment.transaction.import',
        ondelete='restrict',
        index=True,
        tracking=True,
    )

    external_ref = fields.Char(
        index=True,
        tracking=True,
    )

    asset_id = fields.Many2one(related='position_id.asset_id')

    currency_id = fields.Many2one(related='position_id.currency_id')
    company_currency_id = fields.Many2one(related='position_id.company_currency_id')
    company_id = fields.Many2one(related='position_id.company_id')

    payment = fields.Monetary(required=False, currency_field='company_currency_id', tracking=True)
    payment_currency = fields.Monetary(
        compute='_compute_payment_currency',
        inverse='_inverse_payment_currency',
        currency_field='currency_id',
    )

    description = fields.Char()

    exchange_rate = fields.Float(digits='Investment Asset quantity', tracking=True)

    currency_rate_id = fields.Many2one(
        comodel_name='res.currency.rate',
        compute='_compute_currency_rate_id',
        store=True,
        tracking=True,
        readonly=False,
    )
    inverse_company_rate = fields.Float(related='currency_rate_id.inverse_company_rate', readonly=True)

    fee_currency = fields.Monetary(readonly=False,  compute='_compute_fee', currency_field='currency_id')
    fee = fields.Monetary(readonly=False,  compute='_compute_fee', currency_field='company_currency_id')

    quantity = fields.Float(digits='Investment Asset quantity', tracking=True)
    quantity_adjusted = fields.Float(aggregator='avg', compute='_compute_quantity_adjusted', digits='Investment Asset quantity')

    time = fields.Datetime(
        required=True,
        default=fields.Datetime.now,
        index=True,
        tracking=True,
    )
    bypass_lock = fields.Boolean(
        tracking=True,
    )
    is_locked = fields.Boolean(compute='_compute_is_locked')

    profit = fields.Monetary(compute='_compute_profit', currency_field='company_currency_id')

    kanban_quantity = fields.Char(
        compute='_compute_kanban_quantity'
    )


    prediction = fields.Boolean(
        compute='_compute_prediction',
        inverse='_inverse_prediction',
        store=True,
        tracking=True,
    )

    usage = fields.Selection(
        selection=[
            ('record', 'Record'),
            ('prediction', 'Prediction'),
            ('realized', 'Realized Calculation'),
        ],
        required=True,
        default='record',
        tracking=True,
        index=True,
    )

    category_id = fields.Many2one(related='asset_id.category_id', store=True, readonly=True)
    liquid = fields.Boolean(related='category_id.liquid', store=True, readonly=True)
    portfolio_id = fields.Many2one(related='position_id.portfolio_id', store=True, readonly=True)

    ttype = fields.Selection(
        selection=[
            ('buy', 'Buy'),
            ('sell', 'Sell'),
            ('yield', 'Yield'),
            ('cost', 'Cost'),
            ('split', 'Split'),
        ],
        string='Type',
        compute='_compute_report',
        store=True,
        tracking=True,
    )

    is_split = fields.Boolean()

    cash_flow = fields.Monetary(
        compute='_compute_report',
        help="Cash flow related to this transaction. Positive sum means that money went in to the position, negative sum means that money came out of the position.",
        store=True,
        currency_field='company_currency_id'
    )


    _check_exchange_rate = models.Constraint("CHECK(payment = 0 OR exchange_rate <> 0 OR ttype not in ('buy', 'sell'))", "A buy/sell transaction can not be encoded without an exchange rate.")

    @api.onchange('quantity')
    def _onchange_quantity(self):
        if not self.payment and not self.ids:
            self.payment_currency = abs(self.quantity) * self.exchange_rate
            self._inverse_payment_currency()

    def _compute_display_name(self):
        for record in self:
            record.display_name = f'{record.position_id.display_name} @ {record.time}'


    def _compute_kanban_quantity(self):

        def qty_to_str(qty):
            return self.env['ir.qweb.field.float'].value_to_html(qty, {'decimal_precision': 'Investment Asset quantity'}).rstrip('0').rstrip('.').rstrip(',')

        def money_to_str(m, currency):
            qty = qty_to_str(m)
            if currency.position == 'before':
                fmt = '{symbol} {qty}'
            else:
                fmt = '{qty} {symbol}'

            return fmt.format(qty=qty, symbol=currency.symbol)

        units = _("units")
        for record in self:
            record.kanban_quantity = f'{qty_to_str(record.quantity)} {units} @ {money_to_str(record.exchange_rate, record.currency_id)}'

    def find_move(self):
        if not self:
            raise ValidationError(_("No transactions selected!"))

        company = self.env.company

        for record in self:
            if record.move_id:
                raise ValidationError(_("Transaction '%s' already has a move!") % record.display_name)

            if record.company_id != company:
                raise ValidationError(_("Transaction '%s' already belongs to a different company!") % record.display_name)

        dates = set(self.mapped(lambda tx: tx.time.date()))
        if len(dates) != 1:
            raise ValidationError(_("Selected transactions must all be on the same date!"))

        date = next(iter(dates))
        portfolios = set(self.mapped('portfolio_id').ids)
        start = fields.Datetime.to_datetime(date)
        stop = start + timedelta(days=1)
        move = self.env['investment.position.move'].search([
            ('company_id', '=', company.id),
            ('time', '>=', start),
            ('time', '<', stop),
            ('transaction_ids.portfolio_id', 'in', list(portfolios)),
        ]).filtered(lambda m: set(m.transaction_ids.mapped('portfolio_id').ids) == portfolios)

        if len(move) != 1:
            raise ValidationError(_("Expected exactly one move for %s and selected portfolios, found %s.") % (date, len(move)))

        self.write({'move_id': move.id})

        return {
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': move._name,
            'res_id': move.id,
            'target': 'current',
        }

    def make_move(self):
        if not self:
            raise ValidationError(_("No transactions selected!"))

        company = self.env.company

        for record in self:
            if record.move_id:
                raise ValidationError(_("Transaction '%s' already has a move!") % record.display_name)

            if record.company_id != company:
                raise ValidationError(_("Transaction '%s' already belongs to a different company!") % record.display_name)

        time = self[:1].time

        move = self.env['investment.position.move'].create({
            'time': time,
            'company_id': company.id,
            'transaction_ids': [Command.link(t.id) for t in self]
        })
        return {
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': move._name,
            'res_id': move.id,
            'target': 'current',
        }


    def open_form(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': self._name,
            'res_id': self.id,
            'target': 'current',
        }

    def _check_lock_time(self):
        for record in self:
            if record.is_locked:
                raise ValidationError(_("You cannot modify transaction entries (%s UTC) before the company lock time (%s UTC).") % (record.time, record.company_id.investment_lock_time))

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._check_lock_time()
        return records

    def _get_locked_fields(self):
        return {
            'active',
            'position_id',
            'payment',
            'payment_currency',
            'exchange_rate',
            'currency_rate_id',
            'quantity',
            'time',
            'usage',
            'ttype',
            'is_split',
        }

    def write(self, vals):
        do_check = set(vals.keys()) & self._get_locked_fields()
        if do_check: self._check_lock_time()
        result = super().write(vals)
        if do_check: self._check_lock_time()
        return result

    def unlink(self):
        self._check_lock_time()
        return super().unlink()

    @api.depends('company_id.investment_lock_time', 'time', 'bypass_lock')
    def _compute_is_locked(self):
        for record in self:
            record.is_locked = not record.bypass_lock and bool(record.company_id.investment_lock_time and record.time < record.company_id.investment_lock_time)


    @api.depends('usage')
    def _compute_prediction(self):
        for record in self: record.prediction = record.usage == 'prediction'

    def _inverse_prediction(self):
        for record in self: record.usage = 'prediction' if record.prediction else 'record'

    def _fill_daily_price(self):
        Price = self.env['investment.asset.price']
        for transaction in self:
            start_time = transaction.time.replace(hour=0, minute=0, microsecond=0)
            stop_time = transaction.time.replace(hour=23, minute=59, microsecond=0)
            exists = Price.search([('time', '>=', start_time),('time', '<=', stop_time),('asset_id', '=', transaction.asset_id.id),('prediction', '=', False)])
            if transaction.exchange_rate and transaction.quantity and not exists:
                price = transaction.currency_id._convert(
                    from_amount=transaction.exchange_rate,
                    to_currency=transaction.company_currency_id,
                    company=transaction.company_id,
                    date=transaction.time,
                )
                Price.create({
                    'time': start_time.replace(hour=12),
                    'asset_id': transaction.position_id.asset_id.id,
                    'price': price,
                    'transaction_id': transaction.id,
                })
                _logger.info("%s (%s): %s", transaction.asset_id.ticker, transaction.time, price)


    @api.depends('payment')
    def _compute_payment_currency(self):
        for tx in self:
            if tx.currency_id != tx.company_currency_id:
                tx.payment_currency = tx.payment * tx.currency_rate_id.company_rate
            else:
                tx.payment_currency = tx.payment

    def _inverse_payment_currency(self):
        for tx in self:
            if tx.currency_id != tx.company_currency_id:
                tx.payment = tx.payment_currency * tx.currency_rate_id.inverse_company_rate
            else:
                tx.payment = tx.payment_currency


    @api.depends('payment', 'quantity', 'is_split')
    def _compute_report(self):
        for record in self:
            if record.is_split:
                record.ttype = 'split'
                continue
            if record.quantity > 0:
                if record.payment > 0:
                    record.ttype = 'buy'
                    record.cash_flow = record.payment
                else:
                    record.ttype = 'yield'
                    record.cash_flow = -record.payment
            elif record.quantity < 0:
                if record.payment > 0:
                    record.ttype = 'sell'
                    record.cash_flow = -record.payment
                else:
                    record.ttype = 'cost'
                    record.cash_flow = -record.payment # cost has a negative cashflow which needs to be flipped to positive as payment.
            elif record.payment > 0:
                record.ttype = 'yield'
                record.cash_flow = -record.payment
            elif record.payment < 0:
                record.ttype = 'cost'
                record.cash_flow = -record.payment # cost has a negative cashflow which needs to be flipped to positive as payment.
            else: # pragma: no cover
                record.ttype = False
                record.cash_flow = False
                _logger.error("Invalid type: %s", record)


    @api.depends('currency_id', 'time')
    def _compute_currency_rate_id(self):
        # env['investment.position.transaction'].search([])._compute_currency_rate_id()
        for tx in self:
            if tx.currency_id != tx.company_currency_id:
                date = fields.Datetime.context_timestamp(
                    tx.with_context(tz=tx.company_id.partner_id.tz),
                    tx.time,
                ).date()
                rate = tx.env['res.currency.rate'].search([
                    ('currency_id', '=', tx.currency_id.id),
                    ('company_id', '=', tx.company_id.id),
                    ('name', '=', date),
                ])
                if not rate:
                    previous = tx.env['res.currency.rate'].search([
                        ('currency_id', '=', tx.currency_id.id),
                        ('company_id', '=', tx.company_id.id),
                    ], order='name desc', limit=1)
                    rate = tx.env['res.currency.rate'].create({
                        'currency_id': tx.currency_id.id,
                        'name': date,
                        'rate': previous.rate or 0.0,
                        'company_id': tx.company_id.id,
                    })

                tx.currency_rate_id = rate


    @api.depends('payment', 'quantity', 'position_id.last_price_own_currency')
    def _compute_profit(self):
        for tx in self:
            quantity = tx.quantity_adjusted
            if not quantity: # if quantity is 0, the cash flow will be profit.
                tx.profit = tx.payment
            elif tx.ttype == 'split':
                tx.profit = 0.0
            else:
                tx.profit = (tx.position_id.last_price_own_currency - (tx.payment / abs(quantity))) * quantity


    @api.depends('exchange_rate', 'payment', 'quantity', 'time', 'currency_rate_id.rate')
    def _compute_fee(self):
        for tx in self:
            quantity = abs(tx.quantity)
            if not (quantity and tx.payment and tx.exchange_rate and tx.ttype in ['buy', 'sell']):
                tx.fee_currency = 0.0
            else:
                pmt_currency = tx.payment # do the rate conversion manually instead of using payment_currency, as it causes decimal rounding errors
                exh_rate_currency = tx.exchange_rate # company currency
                if tx.currency_rate_id:
                    pmt_currency *= tx.currency_rate_id.company_rate
                    exh_rate_currency *= tx.currency_rate_id.inverse_company_rate

                sign = -1 if tx.ttype == 'sell' else 1
                tx.fee_currency = sign * (pmt_currency/quantity - tx.exchange_rate) * quantity
                tx.fee = sign * (tx.payment/quantity - exh_rate_currency) * quantity

    @api.depends('position_id.asset_id.split_ids', 'position_id.asset_id.split_ids.factor')
    def _compute_quantity_adjusted(self):
        for rec in self:
            splits = rec.asset_id.split_ids
            adjusted = rec.quantity
            for s in splits.filtered(lambda s: rec.time < s.time):
                adjusted *= s.factor
            rec.quantity_adjusted = adjusted
