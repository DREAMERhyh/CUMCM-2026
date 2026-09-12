"""Anytime budget contract tests for Q2 planning."""

import math
from pathlib import Path
import sys
import unittest

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from common.models import BearingObservation
from q2.planner import Q2Config, plan_second_point


def _kept_plan_fields(plan):
    """决策输出子集：预算充足与否都不应改变的逐位结果。"""
    fim = plan["continuous_fim"]
    return {
        "selected_point": tuple(plan["selected_point"]),
        "recommendation_source": plan["recommendation_source"],
        "baseline_point": tuple(plan["baseline"]["selected_point"]),
        "baseline_radius": plan["baseline"]["selected"]["worst_case_radius_m"],
        "fim_status": fim["status"],
        "fim_point": tuple(fim["selected_point"]),
        "fim_radius": fim["selected"]["worst_case_radius_m"],
    }


class AnytimeBudgetTestbench(unittest.TestCase):
    def setUp(self):
        self.observation = BearingObservation((-600.0, -300.0), 1,
                                              "direction", 35.89)

    def test_default_output_is_identical_to_large_budget(self):
        # 默认 8s FIM 子预算下搜索自然完成，预算放大到 300s 不应改变任何决策。
        default = plan_second_point(self.observation)
        large = plan_second_point(
            self.observation,
            config=Q2Config(planning_wall_clock_budget_s=300.0,
                            fim_cpu_time_limit_s=300.0),
        )
        self.assertEqual(_kept_plan_fields(default), _kept_plan_fields(large))
        self.assertFalse(default["continuous_fim"]["timed_out"])
        self.assertFalse(default["planning_timed_out"])

    def test_wall_time_fields_are_reported(self):
        plan = plan_second_point(self.observation)
        used = plan["planning_wall_time_used_s"]
        self.assertGreater(used, 0.0)
        self.assertAlmostEqual(used, plan["planning_cpu_wall_time_s"],
                               places=3)
        self.assertEqual(plan["planning_wall_clock_budget_s"], 120.0)
        self.assertGreater(plan["continuous_fim"]["cpu_wall_time_s"], 0.0)

    def test_tiny_budget_returns_current_incumbent_without_raising(self):
        config = Q2Config(planning_wall_clock_budget_s=0.5,
                          fim_cpu_time_limit_s=0.5,
                          near_optimal_region_cpu_limit_s=0.5)
        plan = plan_second_point(self.observation, config=config)
        self.assertTrue(plan["planning_timed_out"])
        fim = plan["continuous_fim"]
        # 预算耗尽时 FIM 可能以种子解返回（ok），或按既有逻辑降级（unavailable），
        # 但绝不抛异常；推荐点始终是可执行的当前最优。
        self.assertIn(fim["status"], ("ok", "unavailable"))
        if fim["status"] == "ok":
            self.assertTrue(fim["timed_out"])
        candidate_points = {tuple(item["point"])
                            for item in plan["candidates"]}
        self.assertIn(tuple(plan["selected_point"]), candidate_points)
        self.assertIn(tuple(plan["baseline"]["selected_point"]),
                      candidate_points)
        self.assertTrue(math.isfinite(
            plan["selected"]["worst_case_radius_m"]))
        self.assertGreater(plan["selected"]["action_time_s"], 0.0)

    def test_nonpositive_budget_is_rejected(self):
        with self.assertRaises(ValueError):
            plan_second_point(self.observation,
                              config=Q2Config(planning_wall_clock_budget_s=0.0))
        with self.assertRaises(ValueError):
            plan_second_point(self.observation,
                              config=Q2Config(planning_wall_clock_budget_s=-1.0))


if __name__ == "__main__":
    unittest.main()