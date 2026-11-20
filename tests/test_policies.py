import unittest

from parking.policies import FifoPolicy


class FifoPolicyTests(unittest.TestCase):
    def test_empty_head_is_none_and_len_zero(self):
        p = FifoPolicy()
        self.assertIsNone(p.head(now=0.0))
        self.assertEqual(len(p), 0)

    def test_head_is_lowest_ticket_regardless_of_push_order(self):
        p = FifoPolicy()
        p.push(ticket=2, vehicle_id=30, priority=1, now=0.0)
        p.push(ticket=0, vehicle_id=10, priority=1, now=1.0)
        p.push(ticket=1, vehicle_id=20, priority=0, now=2.0)
        self.assertEqual(p.head(now=100.0), 0)
        self.assertEqual(len(p), 3)

    def test_priority_is_ignored_by_fifo(self):
        p = FifoPolicy()
        p.push(ticket=0, vehicle_id=1, priority=1, now=0.0)
        p.push(ticket=1, vehicle_id=2, priority=0, now=0.0)
        self.assertEqual(p.head(now=5.0), 0)

    def test_remove_advances_head(self):
        p = FifoPolicy()
        for t in range(3):
            p.push(ticket=t, vehicle_id=t, priority=1, now=0.0)
        p.remove(0)
        self.assertEqual(p.head(now=1.0), 1)
        p.remove(1)
        self.assertEqual(p.head(now=1.0), 2)
        p.remove(2)
        self.assertIsNone(p.head(now=1.0))
        self.assertEqual(len(p), 0)

    def test_remove_non_head_keeps_head(self):
        p = FifoPolicy()
        for t in range(3):
            p.push(ticket=t, vehicle_id=t, priority=1, now=0.0)
        p.remove(2)
        self.assertEqual(p.head(now=0.0), 0)
        self.assertEqual(len(p), 2)

    def test_remove_unknown_ticket_is_noop(self):
        p = FifoPolicy()
        p.push(ticket=0, vehicle_id=1, priority=1, now=0.0)
        p.remove(99)
        self.assertEqual(len(p), 1)
