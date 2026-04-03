# -*- coding: utf-8 -*-

from odoo.tests import TransactionCase, tagged
from odoo.exceptions import ValidationError
from odoo.tools import mute_logger


@tagged("post_install", "-at_install")
class TestFlightLog(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.FlightLog = cls.env["flight.log"].with_context(tracking_disable=True)
        cls.Airport = cls.env["flight.airport"].with_context(tracking_disable=True)
        cls.Plane = cls.env["flight.plane"].with_context(tracking_disable=True)
        cls.Purpose = cls.env["flight.purpose"].with_context(tracking_disable=True)

        cls.airport_takeoff = cls.Airport.create({"name": "EFHF"})
        cls.airport_landing = cls.Airport.create({"name": "EFHK"})
        cls.plane = cls.Plane.create({"name": "OH-ABC"})
        cls.purpose = cls.env.ref("flight_log.flight_purpose_KOU")

    def _flight_values(self, **overrides):
        values = {
            "name": "Flight %s" % self._testMethodName,
            "airport_takeoff_id": self.airport_takeoff.id,
            "airport_landing_id": self.airport_landing.id,
            "plane_id": self.plane.id,
            "purpose_id": self.purpose.id,
            "date": "2026-01-01",
            "start_time": 10.0,
            "end_time": 11.0,
        }
        values.update(overrides)
        return values

    def _create_flight(self, **overrides):
        return self.FlightLog.create(self._flight_values(**overrides))

    def test_time_helpers_and_search_domains(self):
        self.assertEqual(self.FlightLog.ftime(0.0), "00:00")
        self.assertEqual(self.FlightLog.ftime(13.5), "13:30")
        self.assertAlmostEqual(self.FlightLog.ptime("23:59"), 23.983333333333334)
        with mute_logger("odoo.tools.translate"):
            with self.assertRaises(ValidationError):
                self.FlightLog.ptime("23-59")

        self.assertEqual(
            self.FlightLog._search_date("like", "2026-01"),
            [("date", "like", "2026-01")],
        )
        self.assertEqual(
            self.FlightLog._search_start_time("=", "9"),
            [("start_time", ">=", 9), ("start_time", "<=", 10)],
        )
        self.assertEqual(
            self.FlightLog._search_end_time("=", "12:30"),
            [("end_time", "=", 12.5)],
        )
        with mute_logger("odoo.tools.translate"):
            with self.assertRaises(ValidationError):
                self.FlightLog._search_start_time("=", "bad-value")

    def test_time_constraints_and_skip_validation(self):
        with self.assertRaises(ValidationError):
            self._create_flight(start_time=12.0, end_time=11.0)

        with self.assertRaises(ValidationError):
            self._create_flight(start_time=-1.0, end_time=1.0)

        with self.assertRaises(ValidationError):
            self._create_flight(start_time=23.0, end_time=25.0)

        self._create_flight(name="Existing", start_time=8.0, end_time=9.0)
        with self.assertRaises(ValidationError):
            self._create_flight(name="Overlap", start_time=8.5, end_time=9.5)

        skipped = self._create_flight(
            name="Skip validation",
            start_time=9.5,
            end_time=9.0,
            skip_validation=True,
        )
        self.assertLess(skipped.end_time, skipped.start_time)

    def test_import_fields_duration_and_copy(self):
        record = self._create_flight(name="Import source", start_time=7.25, end_time=8.5)
        self.assertEqual(record.import_start_time, "07:15")
        self.assertEqual(record.import_end_time, "08:30")
        self.assertAlmostEqual(record.duration, 1.25)

        record.write({"import_start_time": "09:00", "import_end_time": "10:45"})
        self.assertAlmostEqual(record.start_time, 9.0)
        self.assertAlmostEqual(record.end_time, 10.75)
        self.assertAlmostEqual(record.duration, 1.75)

        with mute_logger("odoo.tools.translate"):
            with self.assertRaises(ValidationError):
                record.write({"import_start_time": "bad-value"})
        with self.assertRaises(ValidationError):
            record.write({"end_time": False})

        in_memory = self.FlightLog.new({"name": "Draft", "start_time": False, "end_time": False})
        in_memory._compute_duration()
        self.assertFalse(in_memory.duration)

        copied = record.copy()
        self.assertEqual(copied.name, "Import source (copy)")
        self.assertEqual(copied.start_time, 0.0)
        self.assertEqual(copied.end_time, 0.0)

    def test_name_search_import_file_fallback(self):
        airport = self.Airport.create({"name": "Efhk Search"})
        plane = self.Plane.create({"name": "Pawnee Search"})
        purpose = self.Purpose.create({"name": "Search Purpose", "code": "S1"})

        models = [
            (self.Airport, airport.name.lower(), airport.id),
            (self.Plane, plane.name.lower(), plane.id),
            (self.Purpose, purpose.name.lower(), purpose.id),
        ]
        for model, search_term, expected_id in models:
            self.assertFalse(model.name_search(search_term, operator="=", limit=10))
            result = model.with_context(import_file=True).name_search(search_term, operator="=", limit=10)
            self.assertEqual(result[0][0], expected_id)
