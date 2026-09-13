"""Analytical and numerical verification of Q3 scan-stop layouts."""

import math
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from common.models import Action
from q3.coverage import (hub_and_ring_6, hub_ring6_analytical_bounds,
                         nearest_coverage_distance, pure_ring_8,
                         pure_ring8_analytical_bounds, ring7,
                         scan_path_length, scan_phase_virtual_time,
                         verify_coverage_numerically)
from q3.policy import Q3Policy
from runtime.runner import run_policy
from sim.fake import FakeSimulator, FakeSource

COVERAGE_TOLERANCE = 1000.0
DESIGN_RADIUS = 995.0


class ScanLayoutCoverageTestbench(unittest.TestCase):
    def test_ring6_analytical_belt_bound(self):
        bounds = hub_ring6_analytical_bounds()
        self.assertTrue(bounds["passes_design"])
        endpoint = bounds["belt_endpoint_distances_m"]
        # 凸二次函数在闭区间最大值在端点；ρ=1800 端点应不小于 ρ=1000 端点。
        self.assertGreaterEqual(endpoint[1], endpoint[0])
        self.assertLessEqual(bounds["max_belt_distance_m"], DESIGN_RADIUS)
        self.assertEqual(
            bounds["inner_boundary_double_cover"]["nearest_ring_point_count"],
            2,
        )
        self.assertLessEqual(
            bounds["inner_boundary_double_cover"]["distance_to_either_ring_point_m"],
            DESIGN_RADIUS,
        )
        # 独立核算 d(30°,1800)=sqrt(1800² − 2·1200·1800·cos30° + 1200²)。
        rho, r = bounds["belt_range_m"][1], bounds["ring_radius_m"]
        theta = math.radians(30.0)
        independent = math.sqrt(rho*rho - 2*r*rho*math.cos(theta) + r*r)
        self.assertAlmostEqual(bounds["max_belt_distance_m"], independent)
        self.assertAlmostEqual(
            bounds["inner_boundary_double_cover"]["distance_to_either_ring_point_m"],
            math.sqrt(bounds["belt_range_m"][0]**2
                      - 2*r*bounds["belt_range_m"][0]*math.cos(theta) + r*r),
        )

    def test_ring8_analytical_bounds(self):
        bounds = pure_ring8_analytical_bounds()
        self.assertTrue(bounds["passes_design"])
        self.assertAlmostEqual(bounds["center_distance_m"], 960.0)
        self.assertLessEqual(bounds["center_distance_m"], DESIGN_RADIUS)
        self.assertLessEqual(bounds["edge_distance_m"], DESIGN_RADIUS)
        intersection = bounds["adjacent_cover_intersection"]
        self.assertGreaterEqual(intersection["rho_m"], 1800.0)
        # 独立核算 d(22.5°,1800)。
        rho, r = 1800.0, 960.0
        theta = math.radians(22.5)
        independent = math.sqrt(rho*rho - 2*r*rho*math.cos(theta) + r*r)
        self.assertAlmostEqual(bounds["edge_distance_m"], independent)

    def test_ring6_belt_worst_point_is_on_bisector_at_rho_1800(self):
        points = hub_and_ring_6()
        theta = math.radians(30.0)
        for rho in (1000.0, 1300.0, 1600.0, 1800.0):
            point = (rho*math.cos(theta), rho*math.sin(theta))
            distances = sorted(math.dist(point, c) for c in points[1:])
            # 环带上最近的是两个相邻环点，且两者等距（双重覆盖的 Voronoi 边界）。
            self.assertAlmostEqual(distances[0], distances[1], places=6)
            self.assertLessEqual(distances[0], DESIGN_RADIUS)

    def _assert_grid_coverage(self, layout_name, points):
        result = verify_coverage_numerically(points)
        print(f"[数值验证 {layout_name}] 最大最近驻留点距离 "
              f"{result['maximum_distance_m']:.3f} m @ ρ="
              f"{result['worst_rho_m']:.1f} m, θ="
              f"{result['worst_bearing_deg']:.2f}°")
        self.assertTrue(result["passes"],
                        f"{layout_name} 覆盖失败：{result}")
        self.assertLessEqual(result["maximum_distance_m"], COVERAGE_TOLERANCE)

    def test_numeric_grid_coverage_ring7(self):
        self._assert_grid_coverage("ring7", ring7())

    def test_numeric_grid_coverage_hub_ring6(self):
        self._assert_grid_coverage("hub_ring6", hub_and_ring_6())

    def test_numeric_grid_coverage_pure_ring8(self):
        self._assert_grid_coverage("pure_ring8", pure_ring_8())

    def test_ring6_design_margin_holds_on_grid(self):
        # 设计裕量：网格最坏距离也应 ≤ 995（解析最坏点 968.98m，留 ~26m 余量）。
        result = verify_coverage_numerically(hub_and_ring_6())
        self.assertLessEqual(result["maximum_distance_m"], DESIGN_RADIUS)
        print(f"[设计裕量 hub_ring6] {result['maximum_distance_m']:.3f} m "
              f"≤ {DESIGN_RADIUS} m")

    def test_ring8_design_margin_holds_on_grid(self):
        result = verify_coverage_numerically(pure_ring_8())
        self.assertLessEqual(result["maximum_distance_m"], DESIGN_RADIUS)
        print(f"[设计裕量 pure_ring8] {result['maximum_distance_m']:.3f} m "
              f"≤ {DESIGN_RADIUS} m")

    def test_scan_path_lengths(self):
        self.assertAlmostEqual(scan_path_length(ring7()), 9000.0)
        self.assertAlmostEqual(scan_path_length(hub_and_ring_6()), 7200.0)
        expected_pure = 960.0 + 7 * (2.0 * 960.0 * math.sin(math.pi / 8.0))
        self.assertAlmostEqual(scan_path_length(pure_ring_8()), expected_pure)
        # 与环上弦长公式一致性：原点→首驻留点 + 环上相邻弦长之和。
        r = 1200.0
        self.assertAlmostEqual(
            scan_path_length(hub_and_ring_6()),
            r + 5 * (2.0 * r * math.sin(math.pi / 6.0)),
        )
        r = 960.0
        self.assertAlmostEqual(
            scan_path_length(pure_ring_8()),
            r + 7 * (2.0 * r * math.sin(math.pi / 8.0)),
        )

    def test_scan_phase_virtual_time_breakdown(self):
        # ring7：移动 9000/5=1800s，检测 7×20×5=700s，切换 7×19=133s。
        timing = scan_phase_virtual_time(ring7())
        self.assertAlmostEqual(timing["movement_s"], 1800.0)
        self.assertAlmostEqual(timing["measurement_s"], 700.0)
        self.assertAlmostEqual(timing["switching_s"], 133.0)
        self.assertAlmostEqual(timing["total_s"], 2633.0)
        for layout in (hub_and_ring_6(), pure_ring_8()):
            count = len(layout)
            timing = scan_phase_virtual_time(layout)
            self.assertAlmostEqual(timing["measurement_s"], 20.0 * 5.0 * count)
            self.assertAlmostEqual(timing["switching_s"], 19.0 * count)
            self.assertAlmostEqual(
                timing["movement_s"],
                scan_path_length(layout) / 5.0,
            )

    def test_all_layouts_scan_table(self):
        print("\n扫描阶段虚拟时间对比（移动/检测/切换，秒）：")
        print(f"{'布局':<12}{'移动s':>10}{'检测s':>10}{'切换s':>10}{'总计s':>10}")
        for name, points in (
            ("ring7", ring7()),
            ("hub_ring6", hub_and_ring_6()),
            ("pure_ring8", pure_ring_8()),
        ):
            timing = scan_phase_virtual_time(points)
            print(f"{name:<12}{timing['movement_s']:>10.1f}"
                  f"{timing['measurement_s']:>10.1f}"
                  f"{timing['switching_s']:>10.1f}{timing['total_s']:>10.1f}")


class ScanLayoutPolicyTestbench(unittest.TestCase):
    def test_policy_default_is_pure_ring8(self):
        # 2026-09-12 决策：默认布局切换为 pure_ring8（覆盖最坏 984.21m ≤ 995，
        # 扫描阶段比 ring7 省 460s 虚拟时间）。显式 ring7 仍可选择。
        policy = Q3Policy()
        self.assertEqual(policy.scan_layout, "pure_ring8")
        self.assertEqual(policy.coverage_points, list(pure_ring_8()))

    def test_policy_still_supports_explicit_ring7(self):
        policy = Q3Policy(scan_layout="ring7")
        self.assertEqual(policy.scan_layout, "ring7")
        self.assertEqual(policy.coverage_points, list(ring7()))

    def test_policy_selects_new_layouts(self):
        self.assertEqual(Q3Policy(scan_layout="hub_ring6").coverage_points,
                         list(hub_and_ring_6()))
        self.assertEqual(Q3Policy(scan_layout="pure_ring8").coverage_points,
                         list(pure_ring_8()))
        custom = [(10.0, 20.0)]
        self.assertEqual(Q3Policy(coverage_points=custom).coverage_points,
                         custom)

    def test_policy_rejects_unknown_layout(self):
        with self.assertRaises(ValueError):
            Q3Policy(scan_layout="ring9")

    def _run_scan_resolve_smoke(self, layout):
        points = {"hub_ring6": hub_and_ring_6(),
                  "pure_ring8": pure_ring_8()}[layout]
        client = FakeSimulator([FakeSource(3, (1200.0, 100.0), 1000.0)])
        policy = Q3Policy(max_refinements=2, scan_layout=layout)
        with patch("q3.policy.plan_measurement", return_value={
            "selected_point": (500.0, 500.0),
            "recommendation_source": "baseline",
            "baseline": {"selected_point": (500.0, 500.0)},
        }):
            summary = run_policy(policy, client, max_actions=10_000)
        self.assertEqual(summary.cleared_channels, [3])
        self.assertEqual(summary.exit_reason, "user_exit")
        self.assertLess(len(summary.actions), 10_000)
        # 扫描动作数 = 首驻留点 20 + 其余驻留点各 19（已发现频道跳过）±1。
        self.assertGreater(len(summary.actions), 20 * 6)
        return summary

    def test_hub_ring6_policy_finishes_offline(self):
        summary = self._run_scan_resolve_smoke("hub_ring6")
        virtual_expected = (scan_phase_virtual_time(hub_and_ring_6())
                            ["movement_s"])
        self.assertGreater(summary.virtual_time_s, virtual_expected)

    def test_pure_ring8_policy_finishes_offline(self):
        self._run_scan_resolve_smoke("pure_ring8")

    def test_scan_actions_visit_stops_in_order_for_each_layout(self):
        for layout, points in (("hub_ring6", hub_and_ring_6()),
                               ("pure_ring8", pure_ring_8())):
            policy = Q3Policy(scan_layout=layout)
            state = policy.initial_state()
            self.assertEqual(policy.next_action(state).kind, "enter")
            state.pending = None
            state.pending_mode = None
            state.entered = True
            positions = []
            for _ in range(20 * len(points)):
                action = policy.next_action(state)
                self.assertEqual(action.kind, "measure")
                self.assertEqual(action.position, points[len(positions) // 20])
                positions.append(action.position)
                # 模拟响应只推进扫描索引，不动位置。
                state.pending = None
                state.pending_mode = None
                state.scan_channel_index += 1
            # 已发出全部 20×驻留点数 个扫描测量且顺序与布局一致；
            # 驻留点内循环结束后 scan_point_index 将在下一次 next_action 推进。
            self.assertEqual(len(positions), 20 * len(points))
            self.assertEqual(state.phase, "scan")


if __name__ == "__main__":
    unittest.main()