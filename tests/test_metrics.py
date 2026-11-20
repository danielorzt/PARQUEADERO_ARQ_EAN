import unittest

from parking.events import EventKind, SimEvent
from parking.metrics import MetricsCollector, MetricsSummary

K = EventKind


class Feed:
    """Construye SimEvent con números de seq automáticos."""

    def __init__(self, generation=0):
        self.seq = 0
        self.generation = generation

    def ev(self, kind, t, vid=None, occupied=0, queue_len=0, generation=None):
        self.seq += 1
        return SimEvent(seq=self.seq, generation=self.generation if generation is None
                        else generation, t=t, kind=kind, vehicle_id=vid,
                        occupied=occupied, queue_len=queue_len)


def collect(capacity, events, generation=None):
    c = MetricsCollector(capacity, generation)
    for e in events:
        c.apply(e)
    return c.summary()


class MetricsTests(unittest.TestCase):
    def test_empty_run_is_all_zeros(self):
        s = collect(2, [])
        self.assertEqual(s, MetricsSummary(0.0, 0.0, 0.0, 0.0, 0, 0, 0))

    def test_waits_0_2_4_give_avg_2_max_4(self):
        f = Feed()
        events = []
        for vid, wait in ((1, 0.0), (2, 2.0), (3, 4.0)):
            events.append(f.ev(K.ARRIVED, 10.0 * vid, vid))
            events.append(f.ev(K.PARKED, 10.0 * vid + wait, vid, occupied=1))
        s = collect(3, events)
        self.assertEqual(s.avg_wait, 2.0)
        self.assertEqual(s.max_wait, 4.0)
        self.assertEqual(s.parked, 3)

    def test_utilization_is_integral_over_capacity_times_elapsed(self):
        f = Feed()
        events = [f.ev(K.STARTED, 0.0),
                  f.ev(K.ARRIVED, 0.0, 1), f.ev(K.PARKED, 0.0, 1, occupied=1),
                  f.ev(K.ARRIVED, 2.0, 2), f.ev(K.PARKED, 2.0, 2, occupied=2),
                  f.ev(K.DONE, 4.0, 1, occupied=1),
                  f.ev(K.DONE, 8.0, 2, occupied=0)]
        # segundos ocupados: 1*2 + 2*2 + 1*4 = 10 ; capacidad 2 * transcurrido 8 = 16
        s = collect(2, events)
        self.assertAlmostEqual(s.utilization, 10 / 16)
        self.assertEqual(s.elapsed, 8.0)

    def test_utilization_ignores_occupied_default_on_arrived_and_leaving(self):
        # ARRIVED/LEAVING llevan el valor por defecto occupied=0; no deben reiniciar la ocupación.
        f = Feed()
        events = [f.ev(K.STARTED, 0.0),
                  f.ev(K.ARRIVED, 0.0, 1), f.ev(K.PARKED, 0.0, 1, occupied=1),
                  f.ev(K.ARRIVED, 2.0, 2), f.ev(K.ARRIVED, 3.0, 3),
                  f.ev(K.LEAVING, 7.0, 1),
                  f.ev(K.DONE, 8.0, 1, occupied=0)]
        # el vehículo 1 estuvo estacionado los 8 s: 8 segundos ocupados / (capacidad 2 * 8 s)
        self.assertAlmostEqual(collect(2, events).utilization, 0.5)

    def test_utilization_of_real_simulation_matches_parked_done_integral(self):
        import queue
        from parking.config import SimConfig
        from parking.simulation import Simulation
        from tests.helpers import WAIT, drain
        config = SimConfig(capacity=3, num_vehicles=10, seed=42, time_scale=0.01, poll=0.01)
        q = queue.Queue()
        sim = Simulation(config, q)
        sim.start()
        self.assertTrue(sim.finished.wait(WAIT))
        self.assertTrue(sim.join(WAIT))
        events = drain(q)
        occ_events = [e for e in events if e.kind in (K.PARKED, K.DONE)]
        area = sum(a.occupied * (b.t - a.t) for a, b in zip(occ_events, occ_events[1:]))
        elapsed = max(e.t for e in events) - events[0].t
        c = MetricsCollector(config.capacity)
        for e in events:
            c.apply(e)
        # la integral empieza en el primer evento (STARTED); la ocupación es 0 hasta el primer PARKED
        expected = area / (config.capacity * elapsed)
        self.assertGreater(expected, 0.0)
        # t se registra justo antes del Lock del emisor, así que se admite un desfase mínimo
        self.assertAlmostEqual(c.summary().utilization, expected, delta=0.005)

    def test_throughput_is_done_per_simulated_second(self):
        f = Feed()
        events = [f.ev(K.STARTED, 0.0)]
        for i in range(1, 5):
            events.append(f.ev(K.DONE, 2.0 * i, i))
        s = collect(1, events)
        self.assertEqual(s.done, 4)
        self.assertAlmostEqual(s.throughput, 4 / 8.0)

    def test_max_queue_length_is_peak_of_queue_len(self):
        f = Feed()
        events = [f.ev(K.ARRIVED, 0.0, 1, queue_len=1),
                  f.ev(K.ARRIVED, 1.0, 2, queue_len=3),
                  f.ev(K.PARKED, 2.0, 1, occupied=1, queue_len=2)]
        self.assertEqual(collect(1, events).max_queue, 3)

    def test_stale_generation_events_are_ignored(self):
        f = Feed(generation=2)
        events = [f.ev(K.ARRIVED, 0.0, 1, generation=1, queue_len=9),
                  f.ev(K.PARKED, 5.0, 1, generation=1, occupied=1),
                  f.ev(K.ARRIVED, 0.0, 2), f.ev(K.PARKED, 1.0, 2, occupied=1)]
        s = collect(1, events, generation=2)
        self.assertEqual(s.max_wait, 1.0)
        self.assertEqual(s.max_queue, 0)
        self.assertEqual(s.parked, 1)

    def test_apply_returns_false_for_stale_generation(self):
        c = MetricsCollector(1, generation=2)
        self.assertFalse(c.apply(Feed().ev(K.ARRIVED, 0.0, 1, generation=1)))
        self.assertTrue(c.apply(Feed().ev(K.ARRIVED, 0.0, 1, generation=2)))

    def test_cancelled_vehicle_has_no_wait_sample(self):
        f = Feed()
        events = [f.ev(K.ARRIVED, 0.0, 1), f.ev(K.CANCELLED, 3.0, 1)]
        s = collect(1, events)
        self.assertEqual(s.parked, 0)
        self.assertEqual(s.avg_wait, 0.0)
        self.assertEqual(s.cancelled, 1)

    def test_reset_clears_state_and_switches_generation(self):
        c = MetricsCollector(1, generation=0)
        f = Feed()
        c.apply(f.ev(K.ARRIVED, 0.0, 1))
        c.apply(f.ev(K.PARKED, 4.0, 1, occupied=1))
        c.reset(2, generation=1)
        self.assertEqual(c.summary().max_wait, 0.0)
        self.assertFalse(c.apply(f.ev(K.ARRIVED, 0.0, 9, generation=0)))

    def test_rounded_rounds_timing_but_keeps_counts_exact(self):
        s = MetricsSummary(avg_wait=1.23456, max_wait=2.98765, utilization=0.333333,
                           throughput=0.987654, max_queue=3, parked=4, done=4,
                           cancelled=0, elapsed=10.55555)
        r = s.rounded(2)
        self.assertEqual((r.avg_wait, r.max_wait, r.utilization, r.throughput),
                         (1.23, 2.99, 0.33, 0.99))
        self.assertEqual((r.max_queue, r.parked, r.done), (3, 4, 4))

    def test_core_metrics_never_import_tkinter(self):
        import subprocess, sys
        code = ("import sys, parking.metrics, parking.csv_export;"
                "sys.exit(1 if 'tkinter' in sys.modules else 0)")
        self.assertEqual(subprocess.run([sys.executable, "-c", code]).returncode, 0)


if __name__ == "__main__":
    unittest.main()
