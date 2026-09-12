"""Existing Q3 offline checks; no new Q3 test strategy is introduced here."""

import math
from pathlib import Path
import random
import sys
import unittest
from unittest.mock import patch

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from common.models import Action, BearingObservation
from q3.coverage import nearest_coverage_distance, ring7, strip_clear_points
from q3.policy import Q3Policy, Q3State, SourceTrack
from runtime.runner import run_policy
from sim.fake import FakeSimulator, FakeSource
from sim.protocol import build_request_payload


class Q3TheoryTestbench(unittest.TestCase):
    def test_refinement_consumes_q2_hybrid_recommendation(self):
        policy = Q3Policy()
        state = Q3State(position=(10.0, 20.0), current_channel=2)
        track = SourceTrack(
            3,
            observations=[BearingObservation(
                (0.0, 0.0), 3, "direction", 45.0
            )],
            region={"status": "bounded"},
        )
        fake_plan = {
            "selected_point": (80.0, 90.0),
            "recommendation_source": "continuous_fim",
            "baseline": {"selected_point": (1.0, 2.0)},
        }
        with patch("q3.policy.plan_measurement",
                   return_value=fake_plan) as planner:
            self.assertEqual(policy._refinement_point(state, track),
                             (80.0, 90.0))
        self.assertTrue(policy.q2_config.continuous_fim_enabled)
        self.assertEqual(policy.q2_config.fim_cpu_time_limit_s, 6.0)
        self.assertEqual(policy.q2_config.near_optimal_region_mode, "off")
        planner.assert_called_once()

    def test_ring7_covers_random_target_disk_at_radius_1000(self):
        rng = random.Random(20260911)
        centers = ring7()
        worst = 0.0
        for _ in range(5000):
            radius = 1800*math.sqrt(rng.random())
            angle = 2*math.pi*rng.random()
            point = (radius*math.cos(angle), radius*math.sin(angle))
            worst = max(worst, nearest_coverage_distance(point, centers))
        self.assertLessEqual(worst, 1000.0)

    def test_strip_clear_grid_covers_full_bearing_rectangle(self):
        points = list(strip_clear_points((0.0, 0.0), 0.0))
        worst = 0.0
        for x in range(0, 1501, 10):
            for y in (-26.32, -13.16, 0.0, 13.16, 26.32):
                worst = max(worst, min(math.dist((x, y), p) for p in points))
        self.assertLess(worst, 20.0)

    def test_official_199_second_accounting_example(self):
        client = FakeSimulator([])
        actions = [
            Action("enter", "e"),
            Action("measure", "m1", (300.0, 400.0), 1),
            Action("measure", "m2", (300.0, 400.0), 2),
            Action("clear", "c1", (300.0, 0.0), 3),
            Action("measure", "m3", (300.0, 0.0), 2),
        ]
        for action in actions:
            response = client.execute(action)
        self.assertAlmostEqual(response["virtual_time_s"], 199.0)

    def test_request_id_is_idempotent_in_fake_client(self):
        client = FakeSimulator([])
        client.execute(Action("enter", "enter"))
        action = Action("measure", "same", (300.0, 400.0), 1)
        first = client.execute(action)
        second = client.execute(action)
        self.assertEqual(first, second)
        self.assertEqual(client.virtual_time, 105.0)

    def test_official_payload_does_not_leak_internal_fields(self):
        action = Action("measure", "m-1", (1.0, 2.0), 4)
        payload = build_request_payload(action, "team")
        self.assertEqual(set(payload), {"arena_id", "robot_id", "request_id",
                                        "position", "channel"})
        self.assertNotIn("kind", payload)

    def test_q3_policy_finitely_clears_and_certifies_channels_offline(self):
        class CountingQ3Policy(Q3Policy):
            def __init__(self):
                # 显式指定 ring7 并关闭最优停止：本案例的"两次细化"计数
                # 依赖旧的强制 refine 语义；默认布局/最优停止见
                # test_scan_layouts.py 与 test_pruning.py。
                super().__init__(max_refinements=2, scan_layout="ring7",
                                 use_optimal_stop=False)
                self.refinement_plan_count = 0

            def _refinement_point(self, state, track):
                self.refinement_plan_count += 1
                return super()._refinement_point(state, track)

        client = FakeSimulator([FakeSource(3, (1200.0, 100.0), 1000.0)])
        policy = CountingQ3Policy()
        summary = run_policy(policy, client, max_actions=1000)
        self.assertEqual(summary.cleared_channels, [3])
        self.assertEqual(summary.absent_channels,
                         [c for c in range(1, 21) if c != 3])
        self.assertEqual(summary.exit_reason, "user_exit")
        self.assertLess(len(summary.actions), 1000)
        self.assertEqual(policy.refinement_plan_count, 2)


if __name__ == "__main__":
    unittest.main()
