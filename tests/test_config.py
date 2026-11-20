import dataclasses
import unittest

from parking.config import PRESETS, SimConfig


class SimConfigTests(unittest.TestCase):
    def test_defaults_are_valid_and_expose_fields(self):
        cfg = SimConfig()
        cfg.validate()
        self.assertEqual(cfg.capacity, 3)
        self.assertEqual(cfg.policy, "fifo")

    def test_is_frozen(self):
        cfg = SimConfig()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            cfg.capacity = 9

    def test_capacity_below_one_rejected(self):
        for bad in (0, -1):
            with self.assertRaises(ValueError):
                SimConfig(capacity=bad).validate()

    def test_other_invalid_values_rejected(self):
        bad_configs = [
            SimConfig(num_vehicles=-1),
            SimConfig(arrival_gap=(2.0, 1.0)),
            SimConfig(park_time=(0.0, 1.0)),
            SimConfig(time_scale=0),
            SimConfig(policy="lifo"),
            SimConfig(vip_ratio=1.5),
        ]
        for cfg in bad_configs:
            with self.assertRaises(ValueError, msg=repr(cfg)):
                cfg.validate()

    def test_presets_are_valid_simconfigs(self):
        self.assertGreaterEqual(len(PRESETS), 2)
        for name, cfg in PRESETS.items():
            self.assertIsInstance(cfg, SimConfig, name)
            cfg.validate()

    def test_replace_creates_new_config(self):
        cfg = dataclasses.replace(SimConfig(), capacity=7)
        self.assertEqual(cfg.capacity, 7)
