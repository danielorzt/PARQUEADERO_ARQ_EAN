import dataclasses
import queue
import threading
import time
import unittest

from parking.config import SimConfig
from parking.events import EventKind
from parking.simulation import Simulation
from tests.helpers import WAIT, check_log, collect_until, count, drain, gen_threads

FAST = SimConfig(capacity=2, num_vehicles=10, arrival_gap=(0.1, 0.5),
                 park_time=(2.0, 5.0), seed=3, time_scale=0.01, poll=0.01)
SLOW = dataclasses.replace(FAST, park_time=(1000.0, 2000.0), num_vehicles=6)  # ~10 s o más en tiempo real


def run_to_end(testcase, config):
    q = queue.Queue()
    sim = Simulation(config, q)
    sim.start()
    testcase.assertTrue(sim.finished.wait(WAIT), "simulation did not finish")
    testcase.assertTrue(sim.join(WAIT))
    return sim, drain(q)


class StressTests(unittest.TestCase):
    def assert_clean_run(self, config):
        sim, events = run_to_end(self, config)
        check_log(self, events, config.capacity)
        self.assertEqual(count(events, EventKind.ARRIVED), config.num_vehicles)
        self.assertEqual(count(events, EventKind.PARKED), config.num_vehicles)
        self.assertEqual(count(events, EventKind.DONE), config.num_vehicles)
        self.assertEqual(count(events, EventKind.CANCELLED), 0)
        self.assertEqual(count(events, EventKind.FINISHED), 1)
        arrived = [e.vehicle_id for e in events if e.kind is EventKind.ARRIVED]
        self.assertEqual(arrived, sorted(arrived), "tickets follow plan order")
        self.assertEqual(gen_threads(), [])

    def test_ten_vehicles_capacity_two(self):
        self.assert_clean_run(FAST)

    def test_fifty_vehicles_capacity_three(self):
        self.assert_clean_run(dataclasses.replace(FAST, capacity=3, num_vehicles=50))

    def test_invalid_config_rejected(self):
        with self.assertRaises(ValueError):
            Simulation(dataclasses.replace(FAST, capacity=0), queue.Queue())

    def test_add_vehicle_during_run(self):
        q = queue.Queue()
        sim = Simulation(dataclasses.replace(FAST, num_vehicles=2), q)
        sim.start()
        sim.add_vehicle()
        self.assertTrue(sim.finished.wait(WAIT))
        self.assertTrue(sim.join(WAIT))
        events = drain(q)
        self.assertEqual(count(events, EventKind.DONE), 3)
        check_log(self, events, 2)

    def test_add_after_all_vehicles_finished_is_consumed_and_run_finishes(self):
        # Add encolado antes de start: el despachador no ve planes pendientes ni
        # hilos de vehículo activos y una cola de adiciones no vacía. Debe consumir la adición en lugar
        # de girar en `continue` (lo que nunca terminaba hasta llamar a `stop`).
        q = queue.Queue()
        sim = Simulation(dataclasses.replace(FAST, num_vehicles=0), q)
        self.addCleanup(sim.join, WAIT)
        self.addCleanup(sim.stop)
        self.assertTrue(sim.add_vehicle())
        sim.start()
        finished = sim.finished.wait(5.0)
        events = drain(q)
        self.assertTrue(finished, "dispatcher never consumed the queued add")
        self.assertEqual(count(events, EventKind.DONE), 1)
        self.assertEqual(count(events, EventKind.FINISHED), 1)
        self.assertEqual([e.vehicle_id for e in events if e.kind is EventKind.ARRIVED], [1])
        self.assertTrue(sim.join(WAIT))


class LifecycleTests(unittest.TestCase):
    def test_stop_cancels_waiters_and_leaves_no_threads(self):
        q = queue.Queue()
        sim = Simulation(SLOW, q)
        sim.start()
        events = []
        self.assertTrue(collect_until(q, events, lambda ev: count(ev, EventKind.PARKED) >= 2))
        self.assertTrue(collect_until(q, events, lambda ev: count(ev, EventKind.ARRIVED) >= 4))
        sim.stop()
        self.assertTrue(sim.join(WAIT))
        events += drain(q)
        check_log(self, events, 2)
        self.assertEqual(count(events, EventKind.STOPPED), 1)
        self.assertGreaterEqual(count(events, EventKind.CANCELLED), 1)
        self.assertEqual(count(events, EventKind.PARKED), count(events, EventKind.DONE))
        self.assertEqual(gen_threads(), [])
        self.assertTrue(sim.finished.is_set())

    def test_reset_is_non_blocking_and_stale_events_are_droppable(self):
        q = queue.Queue()
        sim = Simulation(SLOW, q)
        sim.start()
        events = []
        self.assertTrue(collect_until(q, events, lambda ev: count(ev, EventKind.PARKED) >= 2))
        old_generation = sim.generation
        began = time.monotonic()
        sim.reset(FAST)
        self.assertLess(time.monotonic() - began, 2.0, "reset must not wait for old threads")
        self.assertEqual(sim.generation, old_generation + 1)
        self.assertTrue(sim.join(WAIT))
        events += drain(q)
        self.assertEqual(gen_threads(), [])
        current = [e for e in events if e.generation == sim.generation]
        stale = [e for e in events if e.generation != sim.generation]
        self.assertEqual([e.kind for e in current], [EventKind.RESET])
        self.assertTrue(stale)
        check_log(self, stale, 2)

    def test_clean_run_after_reset(self):
        q = queue.Queue()
        sim = Simulation(SLOW, q)
        sim.start()
        events = []
        self.assertTrue(collect_until(q, events, lambda ev: count(ev, EventKind.PARKED) >= 1))
        sim.reset(FAST)
        sim.start()
        self.assertTrue(sim.finished.wait(WAIT))
        self.assertTrue(sim.join(WAIT))
        events += drain(q)
        fresh = [e for e in events if e.generation == sim.generation]
        self.assertEqual(count(fresh, EventKind.DONE), FAST.num_vehicles)
        check_log(self, fresh, FAST.capacity)
        self.assertEqual(gen_threads(), [])

    def test_pause_blocks_admission_until_resume(self):
        config = dataclasses.replace(FAST, arrival_gap=(0.0, 0.0), num_vehicles=3)
        q = queue.Queue()
        sim = Simulation(config, q)
        sim.pause()
        sim.start()
        events = []
        self.assertTrue(collect_until(q, events, lambda ev: count(ev, EventKind.ARRIVED) >= 3))
        # Verificación negativa: solo puede pasar de forma espuria, nunca fallar de forma espuria.
        threading.Event().wait(0.15)
        events += drain(q)
        self.assertEqual(count(events, EventKind.PARKED), 0)
        sim.resume()
        self.assertTrue(sim.finished.wait(WAIT))
        self.assertTrue(sim.join(WAIT))
        events += drain(q)
        self.assertEqual(count(events, EventKind.DONE), 3)
        self.assertEqual(count(events, EventKind.PAUSED), 1)
        self.assertEqual(count(events, EventKind.RESUMED), 1)
        check_log(self, events, 2)

    def test_set_speed_emits_event_and_validates(self):
        q = queue.Queue()
        sim = Simulation(dataclasses.replace(FAST, num_vehicles=0), q)
        sim.set_speed(0.5)
        self.assertEqual(count(drain(q), EventKind.SPEED), 1)
        with self.assertRaises(ValueError):
            sim.set_speed(0)

    def test_start_is_idempotent(self):
        q = queue.Queue()
        sim = Simulation(dataclasses.replace(FAST, num_vehicles=3), q)
        sim.start()
        sim.start()
        self.assertTrue(sim.finished.wait(WAIT))
        self.assertTrue(sim.join(WAIT))
        self.assertEqual(count(drain(q), EventKind.STARTED), 1)


if __name__ == "__main__":
    unittest.main()
