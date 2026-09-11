"""Existing Q4 offline checks; no new Q4 test strategy is introduced here."""

import math
from pathlib import Path
import random
import sys
import unittest

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from q4.directional import four_sided_points, grid121, is_visible
from q4.policy import Q4Policy
from runtime.fake_simulator import FakeSimulator, FakeSource
from runtime.runner import run_policy


class Q4TheoryTestbench(unittest.TestCase):
    def test_grid121_covers_random_positions_and_directions(self):
        rng = random.Random(20260911)
        grid = grid121()
        self.assertEqual(len(grid), 121)
        for _ in range(3000):
            radius = 1800*math.sqrt(rng.random())
            angle = 2*math.pi*rng.random()
            source = (radius*math.cos(angle), radius*math.sin(angle))
            direction = 360*rng.random()
            self.assertTrue(any(is_visible(source, direction, sensor)
                                for sensor in grid))

    def test_four_sided_certificate_and_rejection_boundary(self):
        self.assertEqual(len(four_sided_points((10.0, -20.0), 100.0)), 4)
        self.assertEqual(four_sided_points((0.0, 0.0), 150.0), [])
        self.assertEqual(four_sided_points((0.0, 0.0), 850.0), [])

    def test_four_sided_points_have_a_visible_member(self):
        center, radius = (20.0, -30.0), 100.0
        probes = four_sided_points(center, radius)
        for direction in range(0, 360, 5):
            angle = math.radians(direction)
            source = (center[0]+radius*math.cos(angle+1.1),
                      center[1]+radius*math.sin(angle+1.1))
            self.assertTrue(any(is_visible(source, direction, point)
                                for point in probes))

    def test_q4_policy_finitely_clears_directional_source_offline(self):
        client = FakeSimulator([
            FakeSource(7, (1700.0, 0.0), 1000.0, direction_deg=0.0)
        ])
        summary = run_policy(Q4Policy(max_refinements=0), client,
                             max_actions=4000)
        self.assertEqual(summary.cleared_channels, [7])
        self.assertEqual(len(summary.absent_channels), 19)
        self.assertEqual(summary.exit_reason, "user_exit")
        self.assertLess(len(summary.actions), 4000)


if __name__ == "__main__":
    unittest.main()
