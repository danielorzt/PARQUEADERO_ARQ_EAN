import random
import unittest
from dataclasses import replace

from parking.config import SimConfig
from parking.plans import VIP, NORMAL, VehiclePlan, generate_plans


class GeneratePlansTests(unittest.TestCase):
    def test_same_seed_gives_identical_plans(self):
        cfg = SimConfig(num_vehicles=12, seed=7)
        a = generate_plans(cfg, random.Random(cfg.seed))
        b = generate_plans(cfg, random.Random(cfg.seed))
        self.assertEqual(len(a), 12)
        self.assertEqual(a, b)

    def test_different_seed_gives_different_plans(self):
        cfg1 = SimConfig(num_vehicles=12, seed=1)
        cfg2 = replace(cfg1, seed=2)
        self.assertNotEqual(generate_plans(cfg1, random.Random(1)),
                            generate_plans(cfg2, random.Random(2)))

    def test_ids_sequential_and_arrivals_non_decreasing_within_ranges(self):
        cfg = SimConfig(num_vehicles=20, seed=3, arrival_gap=(0.5, 2.0), park_time=(2.0, 5.0))
        plans = generate_plans(cfg, random.Random(3))
        self.assertEqual([p.vehicle_id for p in plans], list(range(1, 21)))
        prev = 0.0
        for p in plans:
            self.assertIsInstance(p, VehiclePlan)
            self.assertGreaterEqual(p.arrival_time - prev, 0.5 - 1e-9)
            self.assertLessEqual(p.arrival_time - prev, 2.0 + 1e-9)
            self.assertGreaterEqual(p.park_time, 2.0)
            self.assertLessEqual(p.park_time, 5.0)
            prev = p.arrival_time

    def test_vip_roll_always_drawn_so_ratio_does_not_shift_gaps(self):
        base = SimConfig(num_vehicles=15, seed=5, vip_ratio=0.0)
        vip = replace(base, vip_ratio=0.5)
        a = generate_plans(base, random.Random(5))
        b = generate_plans(vip, random.Random(5))
        self.assertEqual([p.arrival_time for p in a], [p.arrival_time for p in b])
        self.assertEqual([p.park_time for p in a], [p.park_time for p in b])
        self.assertTrue(all(p.priority == NORMAL for p in a))
        self.assertIn(VIP, [p.priority for p in b])

    def test_all_vip_when_ratio_one(self):
        cfg = SimConfig(num_vehicles=5, vip_ratio=1.0)
        plans = generate_plans(cfg, random.Random(1))
        self.assertTrue(all(p.priority == VIP for p in plans))

    def test_zero_vehicles_gives_empty_plan(self):
        cfg = SimConfig(num_vehicles=0)
        self.assertEqual(generate_plans(cfg, random.Random(1)), [])

    def test_start_id_supports_added_vehicles(self):
        cfg = SimConfig(num_vehicles=2)
        plans = generate_plans(cfg, random.Random(1), start_id=11)
        self.assertEqual([p.vehicle_id for p in plans], [11, 12])
