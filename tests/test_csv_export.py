import csv
import os
import tempfile
import unittest

from parking.csv_export import (EVENT_HEADER, SUMMARY_HEADER, CsvExportError,
                                summary_path_for, write_events, write_summary)
from parking.events import EventKind, SimEvent
from parking.metrics import MetricsSummary

K = EventKind


def sample_events():
    return [SimEvent(1, 0, 0.0, K.STARTED),
            SimEvent(2, 0, 0.5, K.ARRIVED, vehicle_id=1, ticket=1, priority=0, queue_len=1),
            SimEvent(3, 0, 1.25, K.PARKED, vehicle_id=1, ticket=1, slot=0, priority=0,
                     occupied=1),
            SimEvent(4, 0, 9.0, K.DONE, vehicle_id=1, ticket=1, slot=0, priority=0)]


class CsvExportTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = tmp.name

    def test_occupied_cell_is_blank_for_events_that_carry_no_occupancy(self):
        path = os.path.join(self.dir, "events.csv")
        write_events(path, sample_events() + [SimEvent(5, 0, 9.0, K.LEAVING, vehicle_id=1)])
        with open(path, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        by_kind = {r["kind"]: r["occupied"] for r in rows}
        self.assertEqual(by_kind["STARTED"], "")
        self.assertEqual(by_kind["ARRIVED"], "")
        self.assertEqual(by_kind["LEAVING"], "")
        self.assertEqual(by_kind["PARKED"], "1")
        self.assertEqual(by_kind["DONE"], "0")

    def test_events_round_trip_header_and_one_row_per_event_in_order(self):
        path = os.path.join(self.dir, "events.csv")
        events = sample_events()
        write_events(path, events)
        with open(path, newline="", encoding="utf-8") as fh:
            rows = list(csv.reader(fh))
        self.assertEqual(rows[0], list(EVENT_HEADER))
        self.assertEqual(len(rows) - 1, len(events))
        self.assertEqual([int(r[0]) for r in rows[1:]], [e.seq for e in events])
        parked = dict(zip(rows[0], rows[3]))
        self.assertEqual(parked["kind"], "PARKED")
        self.assertEqual(parked["t"], "1.25")
        self.assertEqual(parked["slot"], "0")
        self.assertEqual(dict(zip(rows[0], rows[1]))["vehicle_id"], "")  # None -> vacío

    def test_empty_event_list_writes_header_only(self):
        path = os.path.join(self.dir, "empty.csv")
        write_events(path, [])
        with open(path, newline="", encoding="utf-8") as fh:
            self.assertEqual(list(csv.reader(fh)), [list(EVENT_HEADER)])

    def test_summary_round_trip(self):
        path = os.path.join(self.dir, "summary.csv")
        s = MetricsSummary(2.0, 4.0, 0.5, 0.25, 3, 3, 3, 0, 12.0)
        write_summary(path, s)
        with open(path, newline="", encoding="utf-8") as fh:
            rows = list(csv.reader(fh))
        self.assertEqual(rows[0], list(SUMMARY_HEADER))
        values = {name: value for name, value in rows[1:]}
        self.assertEqual(values["avg_wait"], "2.0")
        self.assertEqual(values["max_queue"], "3")
        self.assertEqual(values["done"], "3")

    def test_unwritable_path_raises_clear_error(self):
        path = os.path.join(self.dir, "missing-dir", "events.csv")
        with self.assertRaises(CsvExportError) as ctx:
            write_events(path, sample_events())
        self.assertIn("missing-dir", str(ctx.exception))

    def test_directory_as_path_raises_clear_error(self):
        with self.assertRaises(CsvExportError):
            write_summary(self.dir, MetricsSummary(0, 0, 0, 0, 0, 0, 0))

    def test_summary_path_is_derived_next_to_events_file(self):
        self.assertEqual(summary_path_for("out/run.csv"),
                         os.path.join("out", "run.summary.csv"))
        self.assertEqual(summary_path_for("run"), "run.summary.csv")


if __name__ == "__main__":
    unittest.main()
