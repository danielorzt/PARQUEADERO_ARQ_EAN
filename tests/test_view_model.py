"""Pruebas del view-model puro de la GUI (sin Tk)."""
import unittest

from parking.config import SimConfig
from parking.events import EventKind, SimEvent
from parking.gui.view_model import ViewModel, build_config


def ev(seq, kind, gen=0, vid=None, ticket=None, slot=None, occupied=0, queue_len=0):
    return SimEvent(seq=seq, generation=gen, t=float(seq), kind=kind, vehicle_id=vid,
                    ticket=ticket, slot=slot, occupied=occupied, queue_len=queue_len)


class ViewModelTests(unittest.TestCase):
    def setUp(self):
        self.vm = ViewModel(capacity=3, generation=0)

    def test_initial_state_is_idle_all_free(self):
        s = self.vm.state()
        self.assertEqual((s.capacity, s.occupied, s.free), (3, 0, 3))
        self.assertEqual(s.phase, "idle")
        self.assertEqual(s.vehicles, [])

    def test_free_and_occupied_follow_events(self):
        self.vm.apply(ev(1, EventKind.STARTED))
        self.vm.apply(ev(2, EventKind.ARRIVED, vid=1, ticket=1, queue_len=1))
        self.vm.apply(ev(3, EventKind.PARKED, vid=1, ticket=1, slot=1, occupied=1))
        s = self.vm.state()
        self.assertEqual((s.occupied, s.free), (1, 2))

    def test_vehicle_states_progress(self):
        self.vm.apply(ev(1, EventKind.ARRIVED, vid=1, ticket=1))
        self.assertEqual(self.vm.state().vehicles[0].state, "WAITING")
        self.vm.apply(ev(2, EventKind.PARKED, vid=1, ticket=1, slot=2, occupied=1))
        row = self.vm.state().vehicles[0]
        self.assertEqual((row.state, row.slot), ("PARKED", 2))
        self.vm.apply(ev(3, EventKind.LEAVING, vid=1, ticket=1, slot=2))  # LEAVING real: occupied=0 por defecto
        self.assertEqual(self.vm.state().vehicles[0].state, "LEAVING")
        self.vm.apply(ev(4, EventKind.DONE, vid=1, ticket=1, slot=2, occupied=0))
        self.assertEqual(self.vm.state().vehicles[0].state, "DONE")
        self.assertEqual(self.vm.state().occupied, 0)

    def test_cancelled_vehicle(self):
        self.vm.apply(ev(1, EventKind.ARRIVED, vid=4, ticket=4))
        self.vm.apply(ev(2, EventKind.CANCELLED, vid=4, ticket=4))
        self.assertEqual(self.vm.state().vehicles[0].state, "CANCELLED")

    def test_rows_sorted_by_vehicle_id(self):
        self.vm.apply(ev(1, EventKind.ARRIVED, vid=2, ticket=2))
        self.vm.apply(ev(2, EventKind.ARRIVED, vid=1, ticket=1))
        self.assertEqual([r.vehicle_id for r in self.vm.state().vehicles], [1, 2])

    def test_buttons_idle(self):
        b = self.vm.state().buttons
        self.assertTrue(b.start)
        self.assertFalse(b.stop)
        self.assertFalse(b.add)
        self.assertTrue(b.reset)

    def test_buttons_running_and_paused(self):
        self.vm.apply(ev(1, EventKind.STARTED))
        b = self.vm.state().buttons
        self.assertEqual((b.start, b.add, b.stop, b.reset), (False, True, True, True))
        self.vm.apply(ev(2, EventKind.PAUSED))
        self.assertEqual(self.vm.state().phase, "paused")
        self.assertTrue(self.vm.state().buttons.add)
        self.vm.apply(ev(3, EventKind.RESUMED))
        self.assertEqual(self.vm.state().phase, "running")

    def test_buttons_after_stop_and_finish(self):
        self.vm.apply(ev(1, EventKind.STARTED))
        self.vm.apply(ev(2, EventKind.FINISHED))
        b = self.vm.state().buttons
        self.assertEqual((b.start, b.add, b.stop, b.reset), (False, False, False, True))
        self.assertEqual(self.vm.state().phase, "finished")
        vm = ViewModel(3, 0)
        vm.apply(ev(1, EventKind.STARTED))
        vm.apply(ev(2, EventKind.STOPPED))
        self.assertEqual(vm.state().phase, "stopped")
        self.assertFalse(vm.state().buttons.stop)

    def test_stale_generation_dropped(self):
        self.vm.reset(capacity=2, generation=1)
        applied = self.vm.apply(ev(5, EventKind.PARKED, gen=0, vid=1, slot=1, occupied=1))
        self.assertFalse(applied)
        s = self.vm.state()
        self.assertEqual((s.occupied, s.vehicles), (0, []))
        self.assertTrue(self.vm.apply(ev(1, EventKind.STARTED, gen=1)))
        self.assertEqual(self.vm.state().phase, "running")

    def test_reset_clears_rows_and_sets_capacity(self):
        self.vm.apply(ev(1, EventKind.ARRIVED, vid=1, ticket=1))
        self.vm.reset(capacity=5, generation=1)
        s = self.vm.state()
        self.assertEqual((s.capacity, s.free, s.phase, s.vehicles), (5, 5, "idle", []))

    def test_queue_len_tracked(self):
        self.vm.apply(ev(1, EventKind.ARRIVED, vid=1, ticket=1, queue_len=4))
        self.assertEqual(self.vm.state().queue_len, 4)

    def test_leaving_does_not_drop_occupied(self):
        # Los eventos LEAVING reales llevan el valor por defecto occupied=0; la ocupación cambia en DONE.
        self.vm.apply(ev(1, EventKind.ARRIVED, vid=1, ticket=0, queue_len=1))
        self.vm.apply(ev(2, EventKind.PARKED, vid=1, ticket=0, slot=1, occupied=1))
        self.vm.apply(ev(3, EventKind.LEAVING, vid=1, ticket=0, slot=1))
        self.assertEqual(self.vm.state().occupied, 1)
        self.assertEqual(self.vm.state().free, 2)
        self.vm.apply(ev(4, EventKind.DONE, vid=1, ticket=0, slot=1, occupied=0))
        self.assertEqual(self.vm.state().occupied, 0)

    def test_arrived_does_not_reset_occupied(self):
        self.vm.apply(ev(1, EventKind.PARKED, vid=1, ticket=0, slot=1, occupied=1))
        self.vm.apply(ev(2, EventKind.ARRIVED, vid=2, ticket=1, queue_len=1))
        self.assertEqual(self.vm.state().occupied, 1)

    def test_queue_len_follows_parked_cancelled_and_done_events(self):
        self.vm.apply(ev(1, EventKind.ARRIVED, vid=1, ticket=0, queue_len=1))
        self.vm.apply(ev(2, EventKind.ARRIVED, vid=2, ticket=1, queue_len=2))
        self.assertEqual(self.vm.state().queue_len, 2)
        self.vm.apply(ev(3, EventKind.PARKED, vid=1, ticket=0, slot=1, occupied=1, queue_len=1))
        self.assertEqual(self.vm.state().queue_len, 1)
        self.vm.apply(ev(4, EventKind.CANCELLED, vid=2, ticket=1, queue_len=0))
        self.assertEqual(self.vm.state().queue_len, 0)
        self.vm.apply(ev(5, EventKind.ARRIVED, vid=3, ticket=2, queue_len=1))
        self.vm.apply(ev(6, EventKind.DONE, vid=1, ticket=0, slot=1, occupied=0, queue_len=0))
        self.assertEqual(self.vm.state().queue_len, 0)

    def test_control_events_do_not_touch_queue_len(self):
        # STARTED/PAUSED/... llevan el valor por defecto queue_len=0 y no deben poner el contador en cero.
        self.vm.apply(ev(1, EventKind.ARRIVED, vid=1, ticket=0, queue_len=3))
        self.vm.apply(ev(2, EventKind.PAUSED))
        self.assertEqual(self.vm.state().queue_len, 3)

    def test_config_editable_unless_running_or_paused(self):
        vm = ViewModel(3, 0)
        self.assertTrue(vm.state().buttons.edit_config)  # en reposo
        vm.apply(ev(1, EventKind.STARTED))
        self.assertFalse(vm.state().buttons.edit_config)
        vm.apply(ev(2, EventKind.PAUSED))
        self.assertFalse(vm.state().buttons.edit_config)
        vm.apply(ev(3, EventKind.RESUMED))
        vm.apply(ev(4, EventKind.FINISHED))
        self.assertTrue(vm.state().buttons.edit_config)
        stopped = ViewModel(3, 0)
        stopped.apply(ev(1, EventKind.STARTED))
        stopped.apply(ev(2, EventKind.STOPPED))
        self.assertTrue(stopped.state().buttons.edit_config)


class BuildConfigTests(unittest.TestCase):
    def test_valid_inputs(self):
        cfg = build_config({"capacity": "4", "vehicles": "8", "seed": "7", "time_scale": "0.5"})
        self.assertIsInstance(cfg, SimConfig)
        self.assertEqual((cfg.capacity, cfg.num_vehicles, cfg.seed, cfg.time_scale), (4, 8, 7, 0.5))

    def test_capacity_below_one_rejected_with_message(self):
        with self.assertRaises(ValueError) as cm:
            build_config({"capacity": "0", "vehicles": "5", "seed": "1", "time_scale": "1"})
        self.assertIn("capacidad", str(cm.exception).lower())

    def test_non_numeric_rejected_with_message(self):
        with self.assertRaises(ValueError) as cm:
            build_config({"capacity": "abc", "vehicles": "5", "seed": "1", "time_scale": "1"})
        self.assertIn("capacidad", str(cm.exception).lower())

    def test_bad_time_scale_rejected(self):
        with self.assertRaises(ValueError):
            build_config({"capacity": "2", "vehicles": "5", "seed": "1", "time_scale": "0"})

    BASE = {"capacity": "2", "vehicles": "5", "seed": "1", "time_scale": "1"}

    def test_arrival_and_park_ranges_map_to_config(self):
        cfg = build_config({**self.BASE, "arrival_min": "0.2", "arrival_max": "1.5",
                            "park_min": "1", "park_max": "3.5"})
        self.assertEqual(cfg.arrival_gap, (0.2, 1.5))
        self.assertEqual(cfg.park_time, (1.0, 3.5))

    def test_ranges_default_to_config_defaults_when_absent(self):
        cfg = build_config(self.BASE)
        self.assertEqual((cfg.arrival_gap, cfg.park_time),
                         (SimConfig().arrival_gap, SimConfig().park_time))

    def test_non_numeric_range_rejected_with_field_name(self):
        for key, word in (("arrival_min", "llegada"), ("arrival_max", "llegada"),
                          ("park_min", "estancia"), ("park_max", "estancia")):
            with self.assertRaises(ValueError, msg=key) as cm:
                build_config({**self.BASE, key: "x"})
            self.assertIn(word, str(cm.exception).lower())

    def test_inverted_range_rejected(self):
        with self.assertRaises(ValueError) as cm:
            build_config({**self.BASE, "arrival_min": "3", "arrival_max": "1"})
        self.assertIn("llegada", str(cm.exception).lower())

    def test_zero_park_time_rejected(self):
        with self.assertRaises(ValueError) as cm:
            build_config({**self.BASE, "park_min": "0", "park_max": "2"})
        self.assertIn("estancia", str(cm.exception).lower())


if __name__ == "__main__":
    unittest.main()
