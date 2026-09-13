"""Q4 融合后离线测试：三角扫描网、探测组、B2 思路注入开关、混合源全清。

本文件以 main 分支 q4 测试为基线移植到 B2 分支，并以 B2 分支的
Q4Policy（探测组+belief/rolling 基线 + M9/A3/TSPN/probe_plan 注入）
为准；所有测试均为本地规则替身，不连接官方模拟器。
"""

import math
import random
import unittest
from pathlib import Path
import sys

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from common.domain import build_region_from_observations
from common.models import BearingObservation
from q3.policy import SourceTrack
from q3.coverage import probe_plan
from q4.belief import Q4Measurement
from q4.directional import (adaptive_four_sided_points, grid121,
                            is_visible, triangular25, triangular37,
                            triangular_scan_mesh)
from q4.policy import Q4Policy
from runtime.runner import run_policy
from sim.fake import FakeSimulator, FakeSource


class Q4GeometryTestbench(unittest.TestCase):
    def test_triangular25_has_structural_and_sample_coverage(self):
        points, triangles = triangular_scan_mesh(
            spacing=985.0, lattice_phase=(0.112, 0.112),
        )
        self.assertEqual(points, triangular25())
        self.assertEqual(len(points), 25)
        self.assertNotIn((0.0, 0.0), points)
        path_length = math.dist((0.0, 0.0), points[0]) + sum(
            math.dist(first, second)
            for first, second in zip(points, points[1:])
        )
        self.assertAlmostEqual(path_length, 24552.14989054634, places=6)
        point_set = set(points)
        for triangle in triangles:
            self.assertTrue(set(triangle) <= point_set)
            for first, second in zip(triangle, triangle[1:]+triangle[:1]):
                self.assertLessEqual(math.dist(first, second), 985.0+1e-7)
        # 粗采样稠密覆盖（轻量版）：全向与定向源在 D(0,1800) 内必被点集发现
        for rho in (0.0, 600.0, 1200.0, 1800.0):
            for angle_index in range(0, 360, 30):
                theta = math.radians(angle_index)
                source = (rho*math.cos(theta), rho*math.sin(theta))
                for direction in range(0, 360, 30):
                    self.assertTrue(any(
                        is_visible(source, direction, point)
                        for point in points
                    ), f"漏检：source={source} dir={direction}")

    def test_triangular37_and_grid121_still_available(self):
        self.assertEqual(len(triangular37()), 37)
        self.assertEqual(len(grid121()), 121)

    def test_adaptive_four_sided_certificate_extends_to_300_m_radius(self):
        points = adaptive_four_sided_points((0.0, 0.0), 300.0,
                                            min_receive_radius=1000.0)
        self.assertTrue(points)
        for point in points:
            self.assertLessEqual(math.hypot(*point), 1000.0-300.0+1e-9)
        # 半径过大时四侧证书不存在，落到三角局部网
        self.assertEqual(adaptive_four_sided_points(
            (0.0, 0.0), 600.0, min_receive_radius=1000.0), [])


class Q4ProbeBundleTestbench(unittest.TestCase):
    def test_probe_bundle_is_not_cut_off_by_individual_measure_limit(self):
        policy = Q4Policy(
            max_refinements=1, directional_rolling_mode="off",
            use_optimal_stop=False,
        )
        state = policy.initial_state()
        state.entered = True
        state.phase = "resolve"
        observations = [
            BearingObservation((1000.0, 0.0), 7, "direction", 180.0),
            BearingObservation((0.0, 1000.0), 7, "direction", 270.0),
        ]
        region = build_region_from_observations(
            observations, error_deg=policy.error_deg, circle_sides=16,
        )
        self.assertGreater(
            region["minimum_enclosing_circle"]["radius"], 19.9,
        )
        state.sources[7] = SourceTrack(
            7, observations=list(observations), region=region,
        )
        state.measure_history[7] = [
            Q4Measurement(item.position, "direction", item.bearing_deg)
            for item in observations
        ]
        attempted = []
        for index in range(3):
            action = policy.next_action(state)
            self.assertEqual(action.kind, "measure")
            self.assertEqual(action.channel, 7)
            attempted.append(tuple(action.position))
            response = {
                "accepted": True,
                "measure_result": "no_signal",
                "virtual_time_s": 100.0 + index,
            }
            policy.apply_response(state, action, response)
            self.assertEqual(state.probe_bundles[7].pending_point, None)
        # 探测组在单个测量上限之外仍保留剩余证书点（剩余 1 点）
        remaining = state.probe_bundles[7].remaining
        self.assertEqual(len(remaining), 1)
        # 第 4 点也 no_signal：证书点耗尽 → 证书失败并转保底清除
        action = policy.next_action(state)
        self.assertEqual(action.kind, "measure")
        policy.apply_response(state, action, {
            "accepted": True, "measure_result": "no_signal",
            "virtual_time_s": 103.0,
        })
        self.assertTrue(state.sources[7].certificate_failed)
        self.assertNotIn(7, state.probe_bundles)

    def test_defaults_carry_b2_injections(self):
        policy = Q4Policy()
        self.assertEqual(policy.scan_mode, "triangular25")
        self.assertEqual(len(policy.coverage_points), 25)
        self.assertTrue(policy.tspn_clear)
        self.assertTrue(policy.use_optimal_stop)
        self.assertEqual(policy.clear_cover, "probe_plan")
        self.assertEqual(policy.failed_clear_remeasure_mode, "gated")
        self.assertEqual(policy.directional_rolling_mode, "scenario")

    def test_switches_can_fall_back_to_legacy(self):
        policy = Q4Policy(use_optimal_stop=False, tspn_clear=False,
                          clear_cover="strip",
                          directional_rolling_mode="off")
        self.assertFalse(policy.use_optimal_stop)
        self.assertFalse(policy.tspn_clear)
        self.assertEqual(policy.clear_cover, "strip")


class Q4OfflineClearTestbench(unittest.TestCase):
    def test_mixed_sources_clear_offline_with_full_certificate(self):
        rng = random.Random(20260913)
        sources = []
        for channel in rng.sample(range(1, 21), 4):
            rho = 1800.0*math.sqrt(rng.random())
            theta = 2.0*math.pi*rng.random()
            direction = None if channel % 3 != 0 else rng.uniform(0.0, 360.0)
            sources.append(FakeSource(
                channel, (rho*math.cos(theta), rho*math.sin(theta)),
                rng.uniform(1000.0, 1500.0), direction_deg=direction))
        summary = run_policy(
            Q4Policy(), FakeSimulator(sources), max_actions=4000,
        )
        self.assertTrue(
            all(s.channel in summary.cleared_channels for s in sources)
        )
        self.assertEqual(
            len(summary.cleared_channels)+len(summary.absent_channels), 20
        )
        self.assertEqual(summary.exit_reason, "user_exit")

    def test_probe_plan_is_bounded_for_large_posterior(self):
        """B2 轮6 蜂窝探针的清除次数上界 1+3k(k+1)，k=ceil(r/20)。"""
        observations = [
            BearingObservation((1000.0, 0.0), 7, "direction", 180.0),
            BearingObservation((0.0, 1000.0), 7, "direction", 270.0),
        ]
        region = build_region_from_observations(
            observations, error_deg=1.005, circle_sides=16,
        )
        radius = region["minimum_enclosing_circle"]["radius"]
        points = probe_plan(region)
        self.assertTrue(points)
        k = max(1, math.ceil(radius/20.0))
        self.assertLessEqual(len(points), 1+3*k*(k+1))


if __name__ == "__main__":
    unittest.main()