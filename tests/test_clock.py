import unittest

from parking.clock import SimClock


class FakeTime:
    """Fuente monótona controlable."""

    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


class SimClockTests(unittest.TestCase):
    def setUp(self):
        self.ft = FakeTime()

    def test_starts_at_zero_and_scale_one_maps_real_to_sim(self):
        clock = SimClock(time_scale=1.0, source=self.ft)
        self.assertEqual(clock.now(), 0.0)
        self.ft.now += 2.5
        self.assertAlmostEqual(clock.now(), 2.5)

    def test_scale_shrinks_real_time(self):
        clock = SimClock(time_scale=0.01, source=self.ft)
        self.ft.now += 0.5
        self.assertAlmostEqual(clock.now(), 50.0)

    def test_real_duration_is_sim_times_scale(self):
        clock = SimClock(time_scale=0.5, source=self.ft)
        self.assertAlmostEqual(clock.real_duration(4.0), 2.0)

    def test_pause_freezes_and_resume_continues(self):
        clock = SimClock(time_scale=1.0, source=self.ft)
        self.ft.now += 1.0
        clock.pause()
        frozen = clock.now()
        self.ft.now += 10.0
        self.assertAlmostEqual(clock.now(), frozen)
        self.assertAlmostEqual(frozen, 1.0)
        clock.resume()
        self.ft.now += 2.0
        self.assertAlmostEqual(clock.now(), 3.0)

    def test_set_scale_does_not_jump_time(self):
        clock = SimClock(time_scale=1.0, source=self.ft)
        self.ft.now += 2.0
        clock.set_scale(0.5)
        self.assertAlmostEqual(clock.now(), 2.0)
        self.ft.now += 1.0
        self.assertAlmostEqual(clock.now(), 4.0)

    def test_double_pause_and_resume_are_idempotent(self):
        clock = SimClock(time_scale=1.0, source=self.ft)
        clock.pause()
        clock.pause()
        self.ft.now += 5.0
        clock.resume()
        clock.resume()
        self.ft.now += 1.0
        self.assertAlmostEqual(clock.now(), 1.0)

    def test_invalid_scale_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            SimClock(time_scale=0)
        self.assertIn("la escala de tiempo debe ser > 0", str(ctx.exception))
        clock = SimClock(time_scale=1.0, source=self.ft)
        with self.assertRaises(ValueError):
            clock.set_scale(-1)

    def test_restart_zeroes_time_and_keeps_pause_state(self):
        clock = SimClock(time_scale=1.0, source=self.ft)
        self.ft.now += 7.0
        clock.restart()
        self.assertAlmostEqual(clock.now(), 0.0)
        self.ft.now += 2.0
        self.assertAlmostEqual(clock.now(), 2.0)
        clock.pause()
        clock.restart()
        self.ft.now += 5.0
        self.assertAlmostEqual(clock.now(), 0.0)
