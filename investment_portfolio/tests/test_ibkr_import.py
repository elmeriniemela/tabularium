# -*- coding: utf-8 -*-

import base64
import csv
import io
from datetime import date, datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from odoo.addons.investment_portfolio.models.ibkr_parse import (
    IBKRParser,
    LedgerRow,
    fmt_decimal,
    is_total_label,
    normalize_time,
    parse_decimal,
)
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestIBKRImport(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.currency_eur = cls.env.ref("base.EUR")
        cls.currency_usd = cls.env.ref("base.USD")
        cls.company.currency_id = cls.currency_eur
        cls.category = cls.env["investment.category"].create({
            "name": "IBKR Test Category",
            "liquid": True,
        })
        cls.portfolio = cls.env["investment.portfolio"].create({
            "name": "IBKR Test Portfolio",
        })
        cls.statement_timezone = ZoneInfo("America/New_York")

    def _statement(self, period_start, period_end, *rows, when_generated="2031-03-31 23:59:59 EST", base_currency="EUR"):
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["Statement", "Data", "WhenGenerated", when_generated])
        writer.writerow(["Statement", "Data", "Period", f"{period_start.strftime('%B %d, %Y')} - {period_end.strftime('%B %d, %Y')}"])
        writer.writerow(["Account Information", "Data", "Base Currency", base_currency])
        writer.writerows(rows)
        return buffer.getvalue()

    def _trade_statement(self):
        return self._statement(
            date(2031, 3, 1),
            date(2031, 3, 31),
            ["Trades", "Header", "", "", "", "", "", "", "", "", "", "Comm/Fee"],
            ["Trades", "Data", "Order", "Stocks", "USD", "AAPL", "2031-03-05, 10:30:45", "2", "10", "", "-20", "-1"],
            ["Deposits & Withdrawals", "Data", "USD", "2031-03-06, 09:00:00", "Transfer", "50"],
            ["Trades", "Header", "", "", "", "", "", "", "", "", "", "Comm in EUR"],
            ["Trades", "Data", "Order", "Forex", "EUR", "EUR.USD", "2031-03-31, 09:43:32", "-983.40678", "1.081", "", "1061.06636", "0"],
            ["Open Positions", "Data", "Summary", "", "", "AAPL", "2"],
            ["Forex Balances", "Data", "", "", "USD", "1090.06636"],
            ["Forex Balances", "Data", "", "", "EUR", "-983.40678"],
        )

    def _simple_trade_statement(
        self,
        asset_category="Stocks",
        symbol="AAPL",
        quantity="2",
        price="10",
        proceeds="-20",
        fee="-1",
        trade_currency="USD",
        commission_label="Comm/Fee",
        when="2031-03-05, 10:30:45",
    ):
        return self._statement(
            date(2031, 3, 1),
            date(2031, 3, 31),
            ["Trades", "Header", "", "", "", "", "", "", "", "", "", commission_label],
            ["Trades", "Data", "Order", asset_category, trade_currency, symbol, when, quantity, price, "", proceeds, fee],
        )

    def _option_multiplier_statement(self):
        return self._statement(
            date(2032, 1, 1),
            date(2032, 1, 31),
            ["Trades", "Header", "", "", "", "", "", "", "", "", "", "Comm/Fee"],
            ["Trades", "Data", "Order", "Equity and Index Options", "USD", "OBIT 17JAN32 50 C", "2032-01-02, 10:00:00", "1", "0.7", "", "-70", "0"],
            ["Open Positions", "Data", "Summary", "", "", "OBIT 17JAN32 50 C", "1"],
            ["Forex Balances", "Data", "", "", "USD", "-70"],
        )

    def _worthless_option_statement(self):
        return self._statement(
            date(2031, 4, 1),
            date(2031, 4, 30),
            ["Trades", "Header", "", "", "", "", "", "", "", "", "", "Comm/Fee"],
            ["Trades", "Data", "Order", "Equity and Index Options", "USD", "WOPT 17APR31 50 C", "2031-04-17, 14:20:00", "-1", "0", "", "0", "0"],
            ["Open Positions", "Data", "Summary", "", "", "WOPT 17APR31 50 C", "0"],
            ["Forex Balances", "Data", "", "", "USD", "0"],
        )

    def _sales_tax_statement(self):
        return self._statement(
            date(2031, 4, 1),
            date(2031, 4, 30),
            ["Fees", "Data", "Broker", "USD", "2031-04-10, 13:00:00", "Monthly Activity Fee", "-1.00"],
            ["Cash Report", "Data", "Starting Cash", "USD", ""],
            ["Cash Report", "Data", "Sales Tax", "USD", "-0.50"],
            ["Cash Report", "Data", "Ending Cash", "USD", "-1.50"],
        )

    def _income_statement(self):
        return self._statement(
            date(2031, 4, 1),
            date(2031, 4, 30),
            ["Fees", "Data", "Total", "USD", "2031-04-09, 10:00:00", "Ignored total", "-9.99"],
            ["Fees", "Data", "Broker", "USD", "2031-04-10, 13:00:00", "Monthly Activity Fee", "-1.00"],
            ["Dividends", "Data", "USD", "2031-04-11, 12:00:00", "Quarterly dividend", "2.50"],
            ["Withholding Tax", "Data", "USD", "2031-04-11, 12:00:00", "Tax withheld", "-0.75"],
            ["Interest", "Data", "USD", "2031-04-12, 08:15:00", "Credit interest", "0.25"],
            ["Cash Report", "Data", "Ending Cash", "BASE CURRENCY SUMMARY", "25.00"],
        )

    def _transfer_statement(self):
        return self._statement(
            date(2031, 5, 1),
            date(2031, 5, 31),
            ["Transfers", "Data", "Stocks", "USD", "ACME", "2031-05-19", "Internal", "IN", "", "", "3", "", "", "", "0"],
            ["Open Positions", "Data", "Summary", "", "", "ACME", "3"],
        )

    def _mismatch_statement(self):
        return self._statement(
            date(2031, 5, 1),
            date(2031, 5, 31),
            ["Open Positions", "Data", "Summary", "", "", "MISS", "2"],
        )

    def _mismatch_with_rows_statement(self):
        return self._statement(
            date(2031, 5, 1),
            date(2031, 5, 31),
            ["Deposits & Withdrawals", "Data", "EUR", "2031-05-10, 09:00:00", "Transfer", "1"],
            ["Open Positions", "Data", "Summary", "", "", "MISS", "2"],
        )

    def _adjustment_statement(self):
        return self._statement(
            date(2031, 6, 1),
            date(2031, 6, 30),
            ["Forex Balances", "Data", "", "", "USD", "10.0005"],
        )

    def _parser(self, rates, starting_balances=None):
        def currency_rate(code, day):
            return rates[(code, day)]
        return IBKRParser(currency_rate, starting_balances)

    def _parse(self, statement, rates, starting_balances=None):
        parser = self._parser(rates, starting_balances=starting_balances)
        return parser.extract_ledger_rows(io.StringIO(statement))

    def _utc_string(self, value):
        return normalize_time(value, self.statement_timezone).astimezone(timezone.utc).replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S")

    def _row_by_description(self, rows, description):
        return next(row for row in rows if row["description"] == description)

    def _create_position(self, name, currency):
        asset = self.env["investment.asset"].create({
            "ticker": name,
            "category_id": self.category.id,
            "currency_id": currency.id,
            "expected_yearly_appreciation": 0.0,
            "plausible_ath_drawdown": 0.0,
        })
        price = self.env["investment.asset.price"].create({
            "asset_id": asset.id,
            "time": datetime(2030, 1, 1, 12, 0, 0),
            "price": 1.0,
        })
        asset.last_price_id = price
        return self.env["investment.position"].create({
            "name": name,
            "asset_id": asset.id,
            "portfolio_id": self.portfolio.id,
            "company_id": self.company.id,
        })

    def _create_usd_rate(self, rate_date, inverse_company_rate):
        self.env["res.currency.rate"].create({
            "name": rate_date,
            "currency_id": self.currency_usd.id,
            "company_id": self.company.id,
            "inverse_company_rate": float(inverse_company_rate),
        })

    def _create_import(self, name, statement, validate_balances=True):
        return self.env["investment.transaction.import"].create({
            "name": name,
            "file": base64.b64encode(statement.encode("utf-8")),
            "source": "ibkr",
            "company_id": self.company.id,
            "portfolio_id": self.portfolio.id,
            "validate_balances": validate_balances,
        })

    def test_normalize_time_supports_date_and_datetime_values(self):
        self.assertEqual(
            normalize_time("2031-03-05", self.statement_timezone),
            datetime(2031, 3, 5, 19, 0, 0, tzinfo=ZoneInfo("Europe/Helsinki")),
        )
        self.assertEqual(
            normalize_time("2031-03-05, 10:30:45", self.statement_timezone),
            datetime(2031, 3, 5, 17, 30, 45, tzinfo=ZoneInfo("Europe/Helsinki")),
        )

    def test_parser_helper_functions_and_ledger_row_exports(self):
        self.assertEqual(parse_decimal("1,234.500"), Decimal("1234.500"))
        self.assertEqual(fmt_decimal(Decimal("10.5000")), "10.5")
        self.assertEqual(fmt_decimal(Decimal("10")), "10")
        self.assertTrue(is_total_label("  Total Fees"))
        self.assertFalse(is_total_label("subtotal"))

        fee_row = LedgerRow(
            ticker="USD",
            time=normalize_time("2031-03-05, 10:30:45", self.statement_timezone),
            quantity=Decimal("-1"),
            price=Decimal("0.9"),
            payment_currency=Decimal("0.9"),
            type="fee",
            description="Monthly fee",
        )
        adjustment_row = LedgerRow(
            ticker="USD",
            time=normalize_time("2031-06-15, 12:00:00", self.statement_timezone),
            quantity=Decimal("0.0005"),
            price=Decimal("0.93"),
            payment_currency=Decimal("0"),
            type="adjustment",
            description="Forex balance precision alignment to statement quantity",
        )

        self.assertTrue(fee_row.export()["external_ref"].startswith("ibkr_tx_fee_USD_"))
        self.assertEqual(adjustment_row.export()["external_ref"], "ibkr_tx_adjustment_USD_20310601")

        fee_row.force_set("cotx_id", "linked")
        self.assertEqual(fee_row.cotx_id, "linked")
        with self.assertRaises(AssertionError):
            fee_row.force_set("ticker", "EUR")

    def test_extract_ledger_rows_raises_on_unsupported_statement_timezone(self):
        statement = "Statement,Data,WhenGenerated,2031-01-01 12:00:00 XYZ\n"
        parser = self._parser({})
        with self.assertRaisesRegex(ValueError, "Unsupported statement timezone abbreviation 'XYZ'"):
            parser.extract_ledger_rows(io.StringIO(statement))

    def test_extract_ledger_rows_ignores_non_importable_rows(self):
        rows = self._parse(
            self._statement(
                date(2031, 7, 1),
                date(2031, 7, 31),
                ["Trades", "Data", "Cancel", "Stocks", "USD", "AAPL", "2031-07-01, 10:00:00", "1", "10", "", "-10", "0"],
                ["Cash Report", "Data", "Ending Cash", "USD"],
                ["Cash Report", "Data", "Starting Cash", "EUR", ""],
                ["Cash Report", "Data", "Sales Tax", "USD", "-0.50"],
                ["Unknown Section", "Header", "ignored"],
                ["Interest", "Data", "USD", "", "No booking time", "0"],
                ["Transfers", "Data", "Stocks", "USD", "ACME"],
            ),
            {},
            starting_balances={},
        )

        self.assertEqual(rows, [])

    def test_trade_statement_keeps_conversion_and_fee_behavior(self):
        rows = self._parse(
            self._trade_statement(),
            {
                ("USD", date(2031, 3, 5)): Decimal("0.9"),
                ("USD", date(2031, 3, 6)): Decimal("0.91"),
                ("USD", date(2031, 3, 31)): Decimal("0.92"),
            },
            starting_balances={},
        )

        self.assertEqual(len(rows), 5)
        self.assertEqual(len(rows), len({row["external_ref"] for row in rows}))

        aapl_asset = self._row_by_description(rows, "Stocks asset leg (AAPL)")
        self.assertEqual(aapl_asset["ticker"], "AAPL")
        self.assertEqual(aapl_asset["time"], self._utc_string("2031-03-05, 10:30:45"))
        self.assertEqual(Decimal(aapl_asset["quantity"]), Decimal("2"))
        self.assertEqual(Decimal(aapl_asset["exchange_rate"]), Decimal("10"))
        self.assertEqual(Decimal(aapl_asset["payment_currency"]), Decimal("21"))

        aapl_currency = self._row_by_description(rows, "Stocks currency leg (AAPL) (fee -1 USD)")
        self.assertEqual(aapl_currency["ticker"], "USD")
        self.assertEqual(Decimal(aapl_currency["quantity"]), Decimal("-21"))
        self.assertEqual(Decimal(aapl_currency["exchange_rate"]), Decimal("0.9"))
        self.assertEqual(Decimal(aapl_currency["payment_currency"]), Decimal("18.9"))

        deposit = self._row_by_description(rows, "Deposits & Withdrawals: Transfer")
        self.assertEqual(deposit["ticker"], "USD")
        self.assertEqual(Decimal(deposit["payment_currency"]), Decimal("50"))
        self.assertEqual(Decimal(deposit["exchange_rate"]), Decimal("0.91"))

        forex_asset = self._row_by_description(rows, "Forex asset leg (EUR.USD)")
        self.assertEqual(forex_asset["ticker"], "USD")
        self.assertEqual(Decimal(forex_asset["quantity"]), Decimal("1061.06636"))
        self.assertEqual(Decimal(forex_asset["exchange_rate"]), Decimal("1") / Decimal("1.081"))
        self.assertEqual(Decimal(forex_asset["payment_currency"]), Decimal("983.40678"))

        forex_currency = self._row_by_description(rows, "Forex currency leg (EUR.USD)")
        self.assertEqual(forex_currency["ticker"], "EUR")
        self.assertEqual(Decimal(forex_currency["quantity"]), Decimal("-983.40678"))
        self.assertEqual(Decimal(forex_currency["exchange_rate"]), Decimal("1"))
        self.assertEqual(Decimal(forex_currency["payment_currency"]), Decimal("983.40678"))

    def test_option_trade_prices_match_multiplier_and_zero_cases(self):
        multiplier_rows = self._parse(
            self._option_multiplier_statement(),
            {
                ("USD", date(2032, 1, 2)): Decimal("0.95"),
            },
            starting_balances={},
        )
        option_buy = self._row_by_description(multiplier_rows, "Equity and Index Options asset leg (OBIT 17JAN32 50 C)")
        self.assertEqual(Decimal(option_buy["exchange_rate"]), Decimal("70"))

        worthless_rows = self._parse(
            self._worthless_option_statement(),
            {
                ("USD", date(2031, 4, 17)): Decimal("0.89"),
            },
            starting_balances={"WOPT 17APR31 50 C": Decimal("1")},
        )
        worthless = self._row_by_description(worthless_rows, "Equity and Index Options asset leg (WOPT 17APR31 50 C)")
        self.assertEqual(Decimal(worthless["exchange_rate"]), Decimal("0"))

    def test_sales_tax_is_appended_on_latest_fee_time(self):
        rows = self._parse(
            self._sales_tax_statement(),
            {
                ("USD", date(2031, 4, 10)): Decimal("0.89"),
            },
            starting_balances={},
        )

        sales_tax = self._row_by_description(rows, "Cash Report: Sales Tax")
        self.assertEqual(sales_tax["time"], self._utc_string("2031-04-10, 13:00:00"))
        self.assertEqual(Decimal(sales_tax["quantity"]), Decimal("-0.5"))
        self.assertEqual(Decimal(sales_tax["exchange_rate"]), Decimal("0.89"))

    def test_income_sections_and_base_currency_summary_are_parsed(self):
        rows = self._parse(
            self._income_statement(),
            {
                ("USD", date(2031, 4, 10)): Decimal("0.89"),
                ("USD", date(2031, 4, 11)): Decimal("0.90"),
                ("USD", date(2031, 4, 12)): Decimal("0.91"),
            },
            starting_balances={"EUR": Decimal("25")},
        )

        descriptions = {row["description"]: row for row in rows}
        self.assertEqual(len(rows), 4)
        self.assertIn("Fees (Broker): Monthly Activity Fee", descriptions)
        self.assertIn("Dividends: Quarterly dividend", descriptions)
        self.assertIn("Withholding Tax: Tax withheld", descriptions)
        self.assertIn("Interest: Credit interest", descriptions)
        self.assertNotIn("Fees: Ignored total", descriptions)

    def test_transfer_rows_use_current_zero_price_behavior(self):
        rows = self._parse(
            self._transfer_statement(),
            {
                ("USD", date(2031, 5, 19)): Decimal("0.87"),
            },
            starting_balances={},
        )

        transfer = self._row_by_description(rows, "Transfers Stocks Internal IN")
        self.assertEqual(transfer["ticker"], "ACME")
        self.assertEqual(Decimal(transfer["exchange_rate"]), Decimal("0"))

    def test_empty_starting_balances_skip_balance_validation(self):
        rows = self._parse(
            self._mismatch_statement(),
            {},
            starting_balances={},
        )
        self.assertEqual(rows, [])

    def test_balance_mismatch_includes_context_when_rows_exist(self):
        with self.assertRaisesRegex(ValueError, "Unexplained balance difference for MISS: 2"):
            self._parse(
                self._mismatch_with_rows_statement(),
                {},
                starting_balances={"EUR": Decimal("0")},
            )

    def test_small_forex_balance_difference_creates_adjustment_row(self):
        rows = self._parse(
            self._adjustment_statement(),
            {
                ("USD", date(2031, 6, 1)): Decimal("0.93"),
            },
            starting_balances={"USD": Decimal("10")},
        )

        self.assertEqual(len(rows), 1)
        adjustment = rows[0]
        self.assertEqual(adjustment["description"], "Forex balance precision alignment to statement quantity")
        self.assertEqual(adjustment["ticker"], "USD")
        self.assertEqual(Decimal(adjustment["quantity"]), Decimal("0.0005"))
        self.assertEqual(Decimal(adjustment["exchange_rate"]), Decimal("0.93"))
        self.assertEqual(adjustment["time"], self._utc_string("2031-06-01"))

    def test_import_compute_vals_list_and_validate_false_branch(self):
        self._create_position("AAPL", self.currency_usd)
        self._create_position("USD", self.currency_usd)
        self._create_usd_rate(date(2031, 3, 5), Decimal("0.9"))

        import_record = self._create_import(
            "2031-03-vals",
            self._simple_trade_statement(),
            validate_balances=False,
        )

        self.assertEqual(len(import_record.vals_list), 2)
        self.assertEqual(len(import_record._parse_ibkr()), 2)

    def test_import_parse_ibkr_resolves_positions_and_converts_values(self):
        aapl = self._create_position("AAPL", self.currency_usd)
        usd = self._create_position("USD", self.currency_usd)
        eur = self._create_position("EUR", self.currency_eur)
        self._create_usd_rate(date(2031, 3, 5), Decimal("0.9"))
        self._create_usd_rate(date(2031, 3, 6), Decimal("0.91"))
        self._create_usd_rate(date(2031, 3, 31), Decimal("0.92"))

        vals_list = self._create_import("2031-03", self._trade_statement())._parse_ibkr()

        self.assertEqual(len(vals_list), 5)
        self.assertEqual({vals["position_id"] for vals in vals_list}, {aapl.id, usd.id, eur.id})

        aapl_vals = next(vals for vals in vals_list if vals["position_id"] == aapl.id)
        self.assertIsInstance(aapl_vals["quantity"], float)
        self.assertIsInstance(aapl_vals["exchange_rate"], float)
        self.assertIsInstance(aapl_vals["payment_currency"], float)
        self.assertEqual(aapl_vals["time"], self._utc_string("2031-03-05, 10:30:45"))
        self.assertTrue(aapl_vals["external_ref"].startswith("ibkr_tx_trade_AAPL_"))

    def test_import_parse_ibkr_requires_positions_and_currency_rates(self):
        self._create_position("AAPL", self.currency_usd)
        self._create_usd_rate(date(2031, 3, 5), Decimal("0.9"))
        self._create_usd_rate(date(2031, 3, 6), Decimal("0.91"))
        self._create_usd_rate(date(2031, 3, 31), Decimal("0.92"))

        import_record = self._create_import("2031-03-missing-position", self._trade_statement())
        with self.assertRaises(ValidationError) as error:
            import_record._parse_ibkr()
        self.assertIn("USD", str(error.exception))

        self._create_position("USD", self.currency_usd)
        self._create_position("EUR", self.currency_eur)

        missing_rate_import = self._create_import("2031-04-missing-rate", self._sales_tax_statement())
        with self.assertRaises(ValidationError) as error:
            missing_rate_import._parse_ibkr()
        self.assertIn("USD", str(error.exception))
        self.assertIn("2031-04-10", str(error.exception))

    def test_import_parse_ibkr_wraps_parser_value_errors(self):
        import_record = self._create_import(
            "2031-03-bad-timezone",
            "Statement,Data,WhenGenerated,2031-01-01 12:00:00 XYZ\n",
        )
        with self.assertRaisesRegex(ValidationError, "2031-03-bad-timezone: Unsupported statement timezone abbreviation 'XYZ'"):
            import_record._parse_ibkr()

    def test_action_import_creates_transactions_and_xmlids(self):
        self._create_position("AAPL", self.currency_usd)
        self._create_position("USD", self.currency_usd)
        self._create_usd_rate(date(2031, 3, 5), Decimal("0.9"))

        import_record = self._create_import("2031-03-import-create", self._simple_trade_statement())
        message_count = len(import_record.message_ids)
        action = import_record.action_import()

        self.assertEqual(len(import_record.transaction_ids), 2)
        self.assertEqual(action["res_model"], "investment.position.transaction")
        self.assertEqual(action["view_mode"], "list")
        self.assertEqual(set(action["domain"][0][2]), set(import_record.transaction_ids.ids))
        self.assertGreater(len(import_record.message_ids), message_count)

        xmlids = self.env["ir.model.data"].search([
            ("module", "=", "__import__"),
            ("res_id", "in", import_record.transaction_ids.ids),
        ])
        self.assertEqual(len(xmlids), 2)

    def test_action_import_updates_existing_unlocked_records(self):
        aapl = self._create_position("AAPL", self.currency_usd)
        self._create_position("USD", self.currency_usd)
        self._create_usd_rate(date(2031, 3, 5), Decimal("0.9"))

        first_import = self._create_import("2031-03-import-a", self._simple_trade_statement())
        first_import.action_import()

        second_import = self._create_import(
            "2031-03-import-b",
            self._simple_trade_statement(asset_category="Equities", price="99"),
        )
        second_import.action_import()

        asset_tx = second_import.transaction_ids.filtered(lambda tx: tx.position_id == aapl)
        self.assertEqual(len(asset_tx), 1)
        self.assertEqual(asset_tx.exchange_rate, 99.0)
        self.assertEqual(asset_tx.description, "Equities asset leg (AAPL)")
        self.assertEqual(len(self.env["investment.position.transaction"].search([("position_id", "=", aapl.id)])), 1)

    def test_action_import_updates_only_unlocked_fields_when_transaction_is_locked(self):
        self.company.partner_id.tz = "UTC"
        aapl = self._create_position("AAPL", self.currency_usd)
        self._create_position("USD", self.currency_usd)
        self._create_usd_rate(date(2031, 3, 5), Decimal("0.9"))

        first_import = self._create_import("2031-03-locked-a", self._simple_trade_statement())
        first_import.action_import()
        asset_tx = first_import.transaction_ids.filtered(lambda tx: tx.position_id == aapl)
        self.assertEqual(asset_tx.exchange_rate, 10.0)

        self.company.investment_lock_time = datetime(2031, 3, 6, 0, 0, 0)
        self.assertTrue(asset_tx.is_locked)

        second_import = self._create_import(
            "2031-03-locked-b",
            self._simple_trade_statement(asset_category="Equities", price="99"),
        )
        second_import.action_import()

        asset_tx = self.env["investment.position.transaction"].browse(asset_tx.id)
        self.assertEqual(asset_tx.exchange_rate, 10.0)
        self.assertEqual(asset_tx.description, "Equities asset leg (AAPL)")
        self.assertEqual(asset_tx.import_id, second_import)
