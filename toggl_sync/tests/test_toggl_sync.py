# -*- coding: utf-8 -*-

import datetime
import threading
from unittest.mock import patch
from xmlrpc.server import SimpleXMLRPCRequestHandler, SimpleXMLRPCServer

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged, TransactionCase
from odoo.tools import mute_logger

from odoo.addons.toggl_sync.models.res_users import TOGGL_SELF
from odoo.addons.toggl_sync.models.toggl_entry import roundto


class _ExportRPCRequestHandler(SimpleXMLRPCRequestHandler):
    rpc_paths = ("/", "/RPC2", "/xmlrpc/object")


class _FakeExportService:
    def __init__(self):
        self.project_tasks = {}
        self.analytic_line_prices = {}
        self.analytic_line_values = {}
        self.next_line_id = 5000

    def execute_kw(self, dbname, uid, pwd, model, method, args, kwargs=None):
        kwargs = kwargs or {}
        del dbname, uid, pwd, kwargs

        if model == "project.task" and method == "search_read":
            ids = args[0][0][2]
            return [self.project_tasks[task_id] for task_id in ids if task_id in self.project_tasks]

        if model == "account.analytic.line" and method == "create":
            values = dict(args[0])
            line_id = self.next_line_id
            self.next_line_id += 1
            self.analytic_line_values[line_id] = values
            self.analytic_line_prices.setdefault(line_id, 80.0)
            return line_id

        if model == "account.analytic.line" and method == "write":
            line_ids, values = args
            if not isinstance(line_ids, list):
                line_ids = [line_ids]
            for line_id in line_ids:
                self.analytic_line_values.setdefault(line_id, {})
                self.analytic_line_values[line_id].update(values)
            return True

        if model == "account.analytic.line" and method == "search_read":
            ids = args[0][0][2]
            return [
                {
                    "id": line_id,
                    "invoice_estimate_unit_price": self.analytic_line_prices.get(line_id, 0.0),
                }
                for line_id in ids
            ]

        raise AssertionError("Unexpected XML-RPC call: %s.%s" % (model, method)) # pragma: no cover


class _FakeHTTPResponse:
    def __init__(self, status_code, payload, *, url, text):
        self.status_code = status_code
        self._payload = payload
        self.url = url
        self.text = text

    def json(self):
        return self._payload


@tagged("post_install", "-at_install")
class TestTogglSync(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Entry = cls.env["toggl.entry"].with_context(tracking_disable=True)
        cls.Task = cls.env["toggl.task"].with_context(tracking_disable=True)
        cls.ImportWizard = cls.env["toggl.import"]
        cls.user = cls.env.user
        cls._toggl_id_seq = 700000

    @classmethod
    def _next_toggl_id(cls):
        cls._toggl_id_seq += 1
        return cls._toggl_id_seq

    @staticmethod
    def _dt(day, hour, minute=0):
        return datetime.datetime(2024, 1, day, hour, minute, 0)

    def _start_export_server(self):
        service = _FakeExportService()
        server = SimpleXMLRPCServer(
            ("127.0.0.1", 0),
            allow_none=True,
            logRequests=False,
            requestHandler=_ExportRPCRequestHandler,
        )
        server.register_instance(service)
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        thread.start()
        self.addCleanup(server.shutdown)
        self.addCleanup(server.server_close)
        self.addCleanup(thread.join, 1)
        url = "http://127.0.0.1:%s/" % server.server_address[1]
        return service, url

    def _set_export_credentials(self, url):
        self.user.write(
            {
                "toggl_export_url": url,
                "toggl_export_dbname": "db",
                "toggl_export_uid": "1",
                "toggl_export_pwd": "pwd",
            }
        )

    def _new_entry(self, **overrides):
        start = overrides.pop("date_start", self._dt(10, 8))
        stop = overrides.pop("date_stop", start + datetime.timedelta(hours=1))
        values = {
            "name": "Work [%s]" % self._next_toggl_id(),
            "description": "Work",
            "checked": True,
            "duration": 1.0,
            "date_start": start,
            "date_stop": stop,
            "toggl_id": self._next_toggl_id(),
        }
        values.update(overrides)
        has_export_credentials = all(
            [
                self.user.toggl_export_url,
                self.user.toggl_export_dbname,
                self.user.toggl_export_uid,
                self.user.toggl_export_pwd,
            ]
        )
        if has_export_credentials:
            return self.Entry.create(values)
        with mute_logger("odoo.addons.toggl_sync.models.toggl_entry"):
            return self.Entry.create(values)

    def test_rounding_actions_urls_and_revenue(self):
        entry = self._new_entry(name="Primary [401]", date_start=self._dt(10, 8), date_stop=self._dt(10, 9))
        self.user.toggl_export_url = "http://example.invalid/"

        self.assertEqual(entry.timesheet_rounding, 5.0 / 60.0)
        self.assertEqual(entry.task_id_regex, r"\[(\d+)\]")

        entry.action_round_up()
        self.assertAlmostEqual(entry.extra_duration, entry.timesheet_rounding)
        entry.action_round_down()
        self.assertAlmostEqual(entry.extra_duration, 0.0)

        entry.action_round_up()
        entry.action_reset_rounding()
        self.assertAlmostEqual(entry.extra_duration, 0.0)

        action = entry.action_open_form()
        self.assertEqual(action["res_id"], entry.id)
        self.assertEqual(action["views"], [[False, "form"]])

        url_action = entry.action_view_task()
        self.assertEqual(url_action["type"], "ir.actions.act_url")
        self.assertIn("model=project.task", url_action["url"])
        self.assertIn("web#id=%s" % entry.task_id.task_id, entry.export_task_url)

        entry.write({"rounded_duration": 2.0, "timesheet_price": 15.0})
        self.assertEqual(entry.revenue, 30.0)

    def test_compute_grouping_and_name_propagation(self):
        first = self._new_entry(
            name="Grouped [451]",
            date_start=self._dt(11, 8),
            date_stop=self._dt(11, 9),
            duration=1.0,
            extra_duration=0.05,
        )
        second = self._new_entry(
            name="Grouped [451]",
            date_start=self._dt(11, 10),
            date_stop=self._dt(11, 10, 30),
            duration=0.5,
        )
        (first + second).recompute_depends()

        parent = (first + second).filtered(lambda e: not e.parent_id)
        child = (first + second).filtered(lambda e: e.parent_id)

        self.assertEqual(len(parent), 1)
        self.assertEqual(len(child), 1)
        self.assertEqual(child.parent_id, parent)
        self.assertEqual(parent.total_duration, 1.5)
        self.assertEqual(child.total_duration, child.duration)
        self.assertEqual(
            parent.rounded_duration,
            roundto(parent.total_duration + parent.extra_duration, base=parent.timesheet_rounding),
        )
        self.assertEqual(child.rounded_duration, roundto(child.duration, base=child.timesheet_rounding))
        self.assertIn(" - ", parent.time_period)
        self.assertIn(", ", parent.time_period)

        parent.write({"name": "Grouped Renamed [451]"})
        child.invalidate_recordset(["name"])
        self.assertEqual(child.name, "Grouped Renamed [451]")

        task = parent.task_id
        self.assertEqual(task.last_entry, second.date_start)

        locked = self._new_entry(name="Locked Entry", date_start=self._dt(12, 8), date_stop=self._dt(12, 9))
        locked.locked = fields.Datetime.now()
        locked.write({"name": "Locked [999]"})
        self.assertFalse(locked.task_id)

    def test_compute_raises_if_multiple_task_ids_are_present(self):
        entry = self._new_entry(name="Single [501]", date_start=self._dt(13, 8), date_stop=self._dt(13, 9))
        with self.assertRaises(UserError):
            entry.write({"name": "Broken [501] [502]"})

    def test_inverse_export_id_and_lock_unlock(self):
        first = self._new_entry(name="ParentChild [601]", date_start=self._dt(14, 8), date_stop=self._dt(14, 9))
        second = self._new_entry(name="ParentChild [601]", date_start=self._dt(14, 9), date_stop=self._dt(14, 10))
        (first + second).recompute_depends()
        parent = (first + second).filtered(lambda e: not e.parent_id)
        child = (first + second).filtered(lambda e: e.parent_id)

        self.assertFalse(parent.export_id)
        child.export_id = 777
        parent.invalidate_recordset(["export_id"])
        child.invalidate_recordset(["export_id"])
        self.assertEqual(parent.export_id, 777)
        self.assertFalse(child.export_id)

        parent.lock()
        self.assertTrue((parent | child).mapped("locked"))
        parent.unlock()
        self.assertFalse(any((parent | child).mapped("locked")))

        parent.recompute_depends()

    def test_task_create_and_fetch_tasks_with_local_xmlrpc(self):
        service, url = self._start_export_server()
        service.project_tasks[1001] = {
            "id": 1001,
            "display_name": "Task 1001",
            "project_id": [88, "Project 88"],
            "sale_line_id": [77, "Sale 77"],
        }
        self._set_export_credentials(url)

        task = self.Task.create({"name": "Task Placeholder", "task_id": 1001})
        self.assertEqual(task.name, "Task 1001")
        self.assertEqual(task.project_id, 88)
        self.assertEqual(task.project_name, "Project 88")
        self.assertEqual(task.sale_line_id, 77)
        self.assertEqual(task.sale_line_name, "Sale 77")

        fallback = self.Task.create({"name": "Unknown Task", "task_id": 1002})
        fallback.fetch_tasks()
        self.assertEqual(fallback.name, "Unknown Task")
        self.assertFalse(fallback.project_id)

    def test_task_create_handles_missing_credentials(self):
        self.user.write(
            {
                "toggl_export_url": False,
                "toggl_export_dbname": False,
                "toggl_export_uid": False,
                "toggl_export_pwd": False,
            }
        )
        with mute_logger("odoo.addons.toggl_sync.models.toggl_entry"):
            task = self.Task.create({"name": "No Export Auth", "task_id": 2001})
        self.assertTrue(task)
        self.assertEqual(task.name, "No Export Auth")

    def test_export_validation_errors(self):
        no_task = self._new_entry(name="No Task Here", duration=1.0, checked=True)
        with self.assertRaisesRegex(UserError, "Task ID missing"):
            no_task.export()

        not_checked = self._new_entry(name="Needs check [2101]", duration=1.0, checked=False)
        with self.assertRaisesRegex(UserError, "not checked"):
            not_checked.export()

        no_amount = self._new_entry(name="Tiny [2102]", duration=0.01, checked=True)
        self.assertLess(no_amount.rounded_duration, no_amount.timesheet_rounding)
        with self.assertRaisesRegex(UserError, "below rounding limit"):
            no_amount.export()

    def test_export_and_timesheet_price_updates_with_local_xmlrpc(self):
        service, url = self._start_export_server()
        service.project_tasks[2201] = {
            "id": 2201,
            "display_name": "Task 2201",
            "project_id": [9, "Project 9"],
            "sale_line_id": [11, "Sale 11"],
        }
        self._set_export_credentials(url)

        entry = self._new_entry(
            name="Billable [2201]",
            description="Billable work",
            duration=1.25,
            checked=True,
            date_start=self._dt(18, 8),
            date_stop=self._dt(18, 9, 15),
        )

        entry.export()
        self.assertTrue(entry.export_id)
        self.assertTrue(entry.locked)
        self.assertEqual(entry.task_id.project_id, 9)
        self.assertEqual(entry.timesheet_price, 80.0)
        self.assertEqual(entry.original_price, 80.0)
        self.assertFalse(entry.price_changed)

        export_id = entry.export_id
        self.assertEqual(service.analytic_line_values[export_id]["task_id"], 2201)
        self.assertEqual(service.analytic_line_values[export_id]["project_id"], 9)

        entry.description = "Billable work updated"
        entry.export()
        self.assertEqual(entry.export_id, export_id)
        self.assertEqual(service.analytic_line_values[export_id]["name"], "Billable work updated")

        service.analytic_line_prices[export_id] = 95.0
        entry.update_timesheet_price()
        self.assertTrue(entry.price_changed)
        self.assertEqual(entry.revenue, entry.rounded_duration * 95.0)

    def test_export_child_reuses_parent_export_line(self):
        service, url = self._start_export_server()
        service.project_tasks[2301] = {
            "id": 2301,
            "display_name": "Task 2301",
            "project_id": [12, "Project 12"],
            "sale_line_id": [15, "Sale 15"],
        }
        self._set_export_credentials(url)

        first = self._new_entry(
            name="Grouped Export [2301]",
            description="Grouped parent",
            checked=True,
            duration=1.0,
            date_start=self._dt(19, 8),
            date_stop=self._dt(19, 9),
        )
        second = self._new_entry(
            name="Grouped Export [2301]",
            description="Grouped child",
            checked=True,
            duration=0.5,
            date_start=self._dt(19, 9),
            date_stop=self._dt(19, 9, 30),
        )
        (first + second).recompute_depends()
        parent = (first + second).filtered(lambda e: not e.parent_id)
        child = (first + second).filtered(lambda e: e.parent_id)

        parent.export()
        export_id = parent.export_id
        next_line_id = service.next_line_id
        child.description = "Grouped child updated"
        child.export()

        self.assertEqual(parent.export_id, export_id)
        self.assertFalse(child.export_id)
        self.assertEqual(service.next_line_id, next_line_id)
        self.assertEqual(service.analytic_line_values[export_id]["name"], "Grouped child updated")

    def test_update_timesheet_price_defaults_to_zero(self):
        service, url = self._start_export_server()
        self._set_export_credentials(url)

        entry = self._new_entry(
            name="Missing price [2401]",
            checked=True,
            date_start=self._dt(23, 8),
            date_stop=self._dt(23, 9),
            export_id=92401,
        )
        self.assertFalse(service.analytic_line_prices.get(entry.export_id))

        entry.update_timesheet_price()
        self.assertEqual(entry.timesheet_price, 0.0)
        self.assertEqual(entry.original_price, 0.0)
        self.assertTrue(entry.price_initialized)
        self.assertFalse(entry.price_changed)

    def test_res_user_fields_and_api_calls(self):
        for field_name in TOGGL_SELF:
            self.assertIn(field_name, self.user.SELF_READABLE_FIELDS)
            self.assertIn(field_name, self.user.SELF_WRITEABLE_FIELDS)

        self.user.write(
            {
                "toggl_export_url": False,
                "toggl_export_dbname": False,
                "toggl_export_uid": False,
                "toggl_export_pwd": False,
            }
        )
        with self.assertRaises(UserError):
            self.user._get_toggl_export_proxy()

        self._set_export_credentials("http://127.0.0.1:1/")
        proxy, dbname, uid, pwd = self.user._get_toggl_export_proxy()
        self.assertEqual(dbname, "db")
        self.assertEqual(uid, "1")
        self.assertEqual(pwd, "pwd")
        self.assertTrue(hasattr(proxy, "execute"))

        self.user.toggl_api_token = "token"
        start = self._dt(20, 8)
        end = self._dt(20, 9)
        success = _FakeHTTPResponse(
            200,
            [{"id": 1}],
            url="https://api.track.toggl.com/api/v9/me/time_entries",
            text="ok",
        )
        with patch("odoo.addons.toggl_sync.models.res_users.requests.get", return_value=success) as mocked_get:
            data = self.user.toggl_time_entries(start, end)
        self.assertEqual(data, [{"id": 1}])
        self.assertEqual(
            mocked_get.call_args.args[0],
            "https://api.track.toggl.com/api/v9/me/time_entries",
        )
        self.assertEqual(mocked_get.call_args.kwargs["auth"], ("token", "api_token"))
        self.assertIn("start_date", mocked_get.call_args.kwargs["params"])
        self.assertIn("end_date", mocked_get.call_args.kwargs["params"])

        failed = _FakeHTTPResponse(
            500,
            {},
            url="https://api.track.toggl.com/api/v9/me/time_entries",
            text="boom",
        )
        with patch("odoo.addons.toggl_sync.models.res_users.requests.get", return_value=failed):
            with self.assertRaisesRegex(UserError, "STATUS=500"):
                self.user.toggl_api_call("get", "time_entries")

    def test_import_wizard_default_without_exported_entries(self):
        wizard = self.ImportWizard.create({})
        now = fields.Datetime.now()
        self.assertLess(wizard.start_date, now)
        self.assertGreater(wizard.end_date, now)

    def test_import_wizard_default_with_existing_exported_entry(self):
        exported = self._new_entry(
            name="Exported [3001]",
            export_id=901,
            date_start=self._dt(21, 8),
            date_stop=self._dt(21, 9),
        )
        wizard = self.ImportWizard.create({})
        self.assertEqual(wizard.start_date, exported.date_stop - datetime.timedelta(days=1))

    def test_import_wizard_import_entries(self):
        existing = self._new_entry(
            name="Old [3301]",
            date_start=self._dt(22, 8),
            date_stop=self._dt(22, 9),
            duration=1.0,
            toggl_id=333001,
        )
        self.user.toggl_api_token = "token"

        payload = [
            {
                "id": 333001,
                "description": "Updated [3301]",
                "start": "2024-01-22T08:00:00+00:00",
                "stop": "2024-01-22T10:00:00+00:00",
                "duration": 7200,
            },
            {
                "id": 333002,
                "description": "New work [3302]  ",
                "start": "2024-01-22T11:00:00+00:00",
                "stop": "2024-01-22T11:45:00+00:00",
                "duration": 2700,
            },
            {
                "id": 333003,
                "description": "Running [3303]",
                "start": "2024-01-22T12:00:00+00:00",
                "duration": 500,
            },
        ]
        response = _FakeHTTPResponse(
            200,
            payload,
            url="https://api.track.toggl.com/api/v9/me/time_entries",
            text="ok",
        )
        with patch("odoo.addons.toggl_sync.models.res_users.requests.get", return_value=response):
            wizard = self.ImportWizard.create(
                {
                    "start_date": self._dt(22, 0),
                    "end_date": self._dt(22, 23),
                }
            )
            with mute_logger("odoo.addons.toggl_sync.models.toggl_entry"):
                action = wizard.import_entries()

        existing.invalidate_recordset(["name", "date_stop", "duration"])
        self.assertEqual(existing.name, "Updated [3301]")
        self.assertEqual(existing.duration, 2.0)

        created = self.Entry.search([("toggl_id", "=", 333002)], limit=1)
        self.assertTrue(created)
        self.assertEqual(created.description, "New work")
        self.assertEqual(created.task_id.task_id, 3302)
        self.assertFalse(self.Entry.search([("toggl_id", "=", 333003)]))

        self.assertEqual(action["res_model"], "toggl.entry")
