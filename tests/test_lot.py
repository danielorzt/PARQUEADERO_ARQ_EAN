import queue
import threading
import unittest

from parking.clock import SimClock
from parking.events import EventEmitter, EventKind
from parking.lot import ParkingLot
from parking.plans import VehiclePlan
from parking.policies import FifoPolicy
from tests.helpers import WAIT, check_log, drain


def make_lot(capacity):
    q = queue.Queue()
    stop, running = threading.Event(), threading.Event()
    running.set()
    lot = ParkingLot(capacity, FifoPolicy(), EventEmitter(q, 0), SimClock(1.0),
                     stop, running, poll=0.01)
    return lot, q, stop, running


class Rig:
    """Ejecuta un hilo por turno; cada uno retiene su espacio hasta que la prueba lo libera."""

    def __init__(self, lot, count):
        self.lot = lot
        self.admitted = [threading.Event() for _ in range(count)]
        self.release = [threading.Event() for _ in range(count)]
        self.results = [None] * count
        self.threads = []
        for i in range(count):
            ticket = lot.issue_ticket(VehiclePlan(i + 1, 0.0, 1.0))
            t = threading.Thread(target=self._run, args=(i, ticket), daemon=True)
            self.threads.append(t)

    def start(self):
        for t in self.threads:
            t.start()

    def _run(self, i, ticket):
        slot = None
        try:
            slot = self.lot.await_admission(ticket)
            self.results[i] = slot
            self.admitted[i].set()
            if slot is not None:
                self.release[i].wait(WAIT)
        finally:
            if slot is not None:
                self.lot.leave(ticket, slot)

    def join(self):
        for t in self.threads:
            t.join(WAIT)
            assert not t.is_alive()


class ParkingLotTests(unittest.TestCase):
    def test_issue_tickets_are_sequential_and_emit_arrived(self):
        lot, q, _, _ = make_lot(2)
        tickets = [lot.issue_ticket(VehiclePlan(i, 0.0, 1.0)) for i in (7, 8, 9)]
        self.assertEqual(tickets, sorted(tickets))
        self.assertEqual(len(set(tickets)), 3)
        events = drain(q)
        self.assertEqual([e.kind for e in events], [EventKind.ARRIVED] * 3)
        self.assertEqual([e.vehicle_id for e in events], [7, 8, 9])
        self.assertEqual([e.queue_len for e in events], [1, 2, 3])

    def test_full_lot_blocks_until_a_vehicle_leaves(self):
        lot, q, _, _ = make_lot(1)
        rig = Rig(lot, 2)
        rig.start()
        self.assertTrue(rig.admitted[0].wait(WAIT))
        # Verificación negativa: solo puede pasar de forma espuria, nunca fallar de forma espuria.
        self.assertFalse(rig.admitted[1].wait(0.1))
        rig.release[0].set()
        self.assertTrue(rig.admitted[1].wait(WAIT))
        rig.release[1].set()
        rig.join()
        check_log(self, drain(q), 1)

    def test_invariants_with_many_threads_and_fifo_order(self):
        lot, q, _, _ = make_lot(2)
        rig = Rig(lot, 8)
        rig.start()
        for i in range(8):
            # el vehículo i solo puede entrar después de que se libere el vehículo i-2 (capacidad 2)
            self.assertTrue(rig.admitted[i].wait(WAIT))
            rig.release[i].set()
        rig.join()
        events = drain(q)
        check_log(self, events, 2)
        self.assertEqual(len([e for e in events if e.kind is EventKind.PARKED]), 8)
        self.assertEqual(len([e for e in events if e.kind is EventKind.DONE]), 8)

    def test_stop_cancels_waiting_vehicles(self):
        lot, q, stop, running = make_lot(1)
        rig = Rig(lot, 3)
        rig.start()
        self.assertTrue(rig.admitted[0].wait(WAIT))
        stop.set()
        lot.wake()
        self.assertTrue(rig.admitted[1].wait(WAIT))
        self.assertTrue(rig.admitted[2].wait(WAIT))
        self.assertIsNone(rig.results[1])
        self.assertIsNone(rig.results[2])
        rig.release[0].set()
        rig.join()
        events = drain(q)
        cancelled = [e.vehicle_id for e in events if e.kind is EventKind.CANCELLED]
        self.assertEqual(sorted(cancelled), [2, 3])
        check_log(self, events, 1)

    def test_paused_lot_admits_nobody_until_resumed(self):
        lot, q, stop, running = make_lot(2)
        running.clear()
        rig = Rig(lot, 1)
        rig.start()
        self.assertFalse(rig.admitted[0].wait(0.1))
        running.set()
        lot.wake()
        self.assertTrue(rig.admitted[0].wait(WAIT))
        rig.release[0].set()
        rig.join()


if __name__ == "__main__":
    unittest.main()
