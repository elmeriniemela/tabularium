# -*- coding: utf-8 -*-
import base64
from datetime import date
from io import BytesIO
from unittest.mock import patch

from psycopg2 import IntegrityError

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, mute_logger

from odoo.addons.cashflow_management.models.cashflow_import import pdftotext


@tagged("cashflow_management", "post_install", "-at_install")
class TestCashflowModels(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Account = cls.env["cashflow.account"]
        cls.Category = cls.env["cashflow.category"]
        cls.Entry = cls.env["cashflow.entry"]
        cls.Import = cls.env["cashflow.import"]
        cls.Parser = cls.env["cashflow.parser"]
        cls.Plan = cls.env["cashflow.plan"]
        cls.PlanLine = cls.env["cashflow.plan.line"]
        cls.Attachment = cls.env["ir.attachment"]

    def _create_parser(self, *, name, code="pass"):
        return self.Parser.create({"name": name, "code": code})

    def _create_account(self, *, name, parser):
        return self.Account.create(
            {
                "name": name,
                "parser_ids": [(6, 0, [parser.id])],
            }
        )

    def _create_attachment(self, *, name, data=b"payload", res_model="res.partner", res_id=1):
        return self.Attachment.create(
            {
                "name": name,
                "type": "binary",
                "datas": base64.b64encode(data),
                "res_model": res_model,
                "res_id": res_id,
            }
        )

    def _create_entry(self, *, name, amount, category, account, parser, attachment, entry_date=None):
        return self.Entry.create(
            {
                "name": name,
                "amount": amount,
                "date": entry_date or fields.Date.today(),
                "category_id": category.id,
                "account_id": account.id,
                "parser_id": parser.id,
                "attachment_id": attachment.id,
            }
        )

    def _build_minimal_pdf(self):
        objects = [
            "<< /Type /Catalog /Pages 2 0 R >>",
            "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 144] >>",
        ]
        parts = [b"%PDF-1.4\n"]
        offsets = []
        for index, body in enumerate(objects, start=1):
            offsets.append(sum(len(chunk) for chunk in parts))
            parts.append(f"{index} 0 obj\n{body}\nendobj\n".encode())

        xref_start = sum(len(chunk) for chunk in parts)
        parts.append(f"xref\n0 {len(objects) + 1}\n".encode())
        parts.append(b"0000000000 65535 f \n")
        for offset in offsets:
            parts.append(f"{offset:010d} 00000 n \n".encode())
        parts.append(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n".encode())
        parts.append(f"startxref\n{xref_start}\n%%EOF\n".encode())
        return b"".join(parts)

    def test_category_sanitize_and_getsert(self):
        category = self.Category.create({"name": "  exPenses   "})
        category.sanitize()
        self.assertEqual(category.name, "Expenses")

        existing = self.Category.getsert(" expenses ")
        self.assertEqual(existing.id, category.id)

        created = self.Category.getsert("  salary ")
        self.assertEqual(created.name, "Salary")

    def test_category_entry_count_updates(self):
        parser = self._create_parser(name="Parser Count")
        account = self._create_account(name="Account Count", parser=parser)
        category = self.Category.create({"name": "Utilities"})
        attachment = self._create_attachment(name="count.txt")

        entry = self._create_entry(
            name="Utility bill",
            amount=-12.5,
            category=category,
            account=account,
            parser=parser,
            attachment=attachment,
        )
        self.assertEqual(category.entry_count, 1)

        entry.unlink()
        category.invalidate_recordset(["entry_count"])
        self.assertEqual(category.entry_count, 0)

    def test_account_unique_name_constraint(self):
        self.Account.create({"name": "Main Account"})
        with mute_logger("odoo.sql_db"), self.assertRaises(IntegrityError), self.cr.savepoint():
            self.Account.create({"name": "Main Account"})

    def test_entry_type_related_active_and_zero_amount_constraint(self):
        parser = self._create_parser(name="Parser Entry")
        account = self._create_account(name="Account Entry", parser=parser)
        category = self.Category.create({"name": "Operations"})
        attachment = self._create_attachment(name="entry.txt")

        deposit = self._create_entry(
            name="Deposit",
            amount=10.0,
            category=category,
            account=account,
            parser=parser,
            attachment=attachment,
        )
        withdrawal = self._create_entry(
            name="Withdrawal",
            amount=-1.0,
            category=category,
            account=account,
            parser=parser,
            attachment=attachment,
        )

        self.assertEqual(deposit.entry_type, "deposit")
        self.assertEqual(withdrawal.entry_type, "withdrawal")
        self.assertTrue(deposit.active)

        account.active = False
        deposit.invalidate_recordset(["active"])
        self.assertFalse(deposit.active)

        with mute_logger("odoo.sql_db"), self.assertRaises(IntegrityError), self.cr.savepoint():
            self._create_entry(
                name="Zero",
                amount=0.0,
                category=category,
                account=account,
                parser=parser,
                attachment=attachment,
            )

    def test_plan_line_default_date_balance_and_zero_constraint(self):
        with patch(
            "odoo.addons.cashflow_management.models.cashflow_plan.fields.Date.today",
            return_value=date(2024, 1, 10),
        ):
            self.assertEqual(self.PlanLine._default_date(), date(2024, 1, 15))

        with patch(
            "odoo.addons.cashflow_management.models.cashflow_plan.fields.Date.today",
            return_value=date(2024, 1, 20),
        ):
            self.assertEqual(self.PlanLine._default_date(), date(2024, 2, 15))

        plan = self.Plan.create({"name": "Plan A"})
        line_one = self.PlanLine.create(
            {"plan_id": plan.id, "name": "Income", "date": date(2024, 1, 1), "amount": 100.0, "sequence": 1}
        )
        line_two = self.PlanLine.create(
            {"plan_id": plan.id, "name": "Cost", "date": date(2024, 1, 2), "amount": -40.0, "sequence": 2}
        )
        self.assertEqual(line_one.balance, 100.0)
        self.assertEqual(line_two.balance, 60.0)

        with mute_logger("odoo.sql_db"), self.assertRaises(IntegrityError), self.cr.savepoint():
            self.PlanLine.create({"plan_id": plan.id, "name": "Zero", "amount": 0.0})

    def test_parser_validation_and_delete_files(self):
        parser = self._create_parser(name="Parser Files", code="x = 1")

        with self.assertRaises(ValidationError):
            self._create_parser(name="Parser Invalid", code="if True print('broken')")

        attachment = self._create_attachment(
            name="old.csv",
            data=b"old",
            res_model="cashflow.parser",
            res_id=parser.id,
        )
        self.assertTrue(attachment.exists())
        parser.delete_files()
        self.assertFalse(attachment.exists())

    def test_import_compute_active_ids_uses_context(self):
        parser = self._create_parser(name="Parser Context")
        account = self._create_account(name="Account Context", parser=parser)

        parser_ctx_wizard = self.Import.with_context(
            active_model="cashflow.parser",
            active_ids=[parser.id],
        ).new({})
        parser_ctx_wizard._compute_active_ids()
        self.assertEqual(parser_ctx_wizard.parser_id.id, parser.id)
        self.assertEqual(parser_ctx_wizard.account_id.id, account.id)

        account_ctx_wizard = self.Import.with_context(
            active_model="cashflow.account",
            active_ids=[account.id],
        ).new({})
        account_ctx_wizard._compute_active_ids()
        self.assertEqual(account_ctx_wizard.account_id.id, account.id)
        self.assertEqual(account_ctx_wizard.parser_id.id, parser.id)

        pinned_parser = self._create_parser(name="Pinned Parser")
        pinned_account = self._create_account(name="Pinned Account", parser=pinned_parser)
        keep_values_wizard = self.Import.with_context(
            active_model="cashflow.parser",
            active_ids=[parser.id],
        ).new({"parser_id": pinned_parser.id, "account_id": pinned_account.id})
        keep_values_wizard._compute_active_ids()
        self.assertEqual(keep_values_wizard.parser_id.id, pinned_parser.id)
        self.assertEqual(keep_values_wizard.account_id.id, pinned_account.id)

    def test_import_file_creates_entries_and_relinks_attachments(self):
        parser = self._create_parser(
            name="Parser Import",
            code="""
category = self.env['cashflow.category'].getsert('imported')
add_entry({
    'name': fname,
    'amount': 15.5,
    'date': '2024-01-01',
    'category_id': category.id,
    'raw': fp.read().decode(),
    'identifier': fname,
})
""",
        )
        account = self._create_account(name="Account Import", parser=parser)
        attachment_one = self._create_attachment(name="one.csv", data=b"first")
        attachment_two = self._create_attachment(name="two.csv", data=b"second")
        wizard = self.Import.create(
            {
                "parser_id": parser.id,
                "account_id": account.id,
                "attachment_ids": [(6, 0, [attachment_one.id, attachment_two.id])],
            }
        )

        wizard.import_file()

        entries = self.Entry.search([("attachment_id", "in", [attachment_one.id, attachment_two.id])])
        self.assertEqual(len(entries), 2)
        self.assertEqual(set(entries.mapped("name")), {"one.csv", "two.csv"})
        self.assertEqual(set(entries.mapped("raw")), {"first", "second"})
        self.assertEqual(set(entries.mapped("identifier")), {"one.csv", "two.csv"})
        self.assertEqual(set(entries.mapped("account_id").ids), {account.id})
        self.assertEqual(set(entries.mapped("parser_id").ids), {parser.id})

        self.assertEqual(attachment_one.res_model, "cashflow.parser")
        self.assertEqual(attachment_one.res_id, parser.id)
        self.assertEqual(attachment_two.res_model, "cashflow.parser")
        self.assertEqual(attachment_two.res_id, parser.id)

    def test_pdftotext_handles_empty_and_non_empty_input(self):
        self.assertEqual(pdftotext(BytesIO(b"")), b"")
        non_empty = pdftotext(BytesIO(self._build_minimal_pdf()))
        self.assertIsInstance(non_empty, bytes)
