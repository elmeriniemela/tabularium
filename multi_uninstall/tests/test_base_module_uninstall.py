# -*- coding: utf-8 -*-

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestBaseModuleUninstall(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        module_model = cls.env["ir.module.module"]
        cls.multi_uninstall_module = module_model.search(
            [("name", "=", "multi_uninstall")],
            limit=1,
        )
        cls.base_module = module_model.search([("name", "=", "base")], limit=1)
        cls.web_module = module_model.search([("name", "=", "web")], limit=1)

    def test_action_next_returns_followup_wizard_action(self):
        wizard = self.env["base.module.uninstall"].create(
            {"module_id": self.multi_uninstall_module.id}
        )

        action = wizard.with_context(
            active_ids=[
                self.multi_uninstall_module.id,
                self.base_module.id,
                self.web_module.id,
            ],
        ).action_next()

        self.assertEqual(action["res_model"], "base.module.uninstall")
        self.assertEqual(action["type"], "ir.actions.act_window")
        self.assertEqual(action["target"], "new")
        self.assertEqual(set(action["context"]["active_ids"]), {self.base_module.id, self.web_module.id})
        self.assertIn(action["context"]["active_id"], action["context"]["active_ids"])
        self.assertTrue(action["context"]["default_show_all"])
        self.assertEqual(action["context"]["default_module_id"], action["context"]["active_id"])
        self.assertNotIn(self.multi_uninstall_module.id, action["context"]["active_ids"])

    def test_action_next_returns_none_when_no_modules_left(self):
        wizard = self.env["base.module.uninstall"].create(
            {"module_id": self.multi_uninstall_module.id}
        )

        action = wizard.with_context(
            active_ids=[self.multi_uninstall_module.id],
        ).action_next()

        self.assertFalse(action)

    def test_action_uninstall_raises_when_module_operations_are_blocked(self):
        wizard = self.env["base.module.uninstall"].create(
            {"module_id": self.multi_uninstall_module.id}
        )

        with self.assertRaises(UserError):
            wizard.action_uninstall()
