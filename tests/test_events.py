import dataclasses
import queue
import threading
import unittest

from parking.events import EventEmitter, EventKind, SimEvent


class SimEventTests(unittest.TestCase):
    def test_event_is_frozen(self):
        ev = SimEvent(seq=1, generation=0, t=0.0, kind=EventKind.ARRIVED, vehicle_id=1)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            ev.seq = 5

    def test_event_kinds_cover_design(self):
        names = {k.name for k in EventKind}
        expected = {"STARTED", "ARRIVED", "PARKED", "LEAVING", "DONE", "CANCELLED",
                    "PAUSED", "RESUMED", "SPEED", "STOPPED", "RESET", "FINISHED"}
        self.assertEqual(names, expected)

    def test_optional_fields_default_to_none(self):
        ev = SimEvent(seq=1, generation=0, t=0.0, kind=EventKind.STARTED)
        self.assertIsNone(ev.vehicle_id)
        self.assertIsNone(ev.slot)
        self.assertEqual(ev.occupied, 0)


class EventEmitterTests(unittest.TestCase):
    def test_emit_assigns_increasing_seq_and_enqueues(self):
        q = queue.Queue()
        em = EventEmitter(q, generation=3)
        e1 = em.emit(EventKind.ARRIVED, t=0.5, vehicle_id=1, ticket=0)
        e2 = em.emit(EventKind.PARKED, t=1.0, vehicle_id=1, ticket=0, slot=0, occupied=1)
        self.assertEqual((e1.seq, e2.seq), (1, 2))
        self.assertEqual(e1.generation, 3)
        self.assertEqual(e2.slot, 0)
        self.assertIs(q.get_nowait(), e1)
        self.assertIs(q.get_nowait(), e2)
        self.assertTrue(q.empty())

    def test_concurrent_emit_has_unique_seq_matching_queue_order(self):
        q = queue.Queue()
        em = EventEmitter(q, generation=0)

        def work():
            for _ in range(100):
                em.emit(EventKind.ARRIVED, t=0.0)

        threads = [threading.Thread(target=work) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(5)
        seqs = []
        while not q.empty():
            seqs.append(q.get_nowait().seq)
        self.assertEqual(len(seqs), 800)
        self.assertEqual(seqs, list(range(1, 801)))
