"""Q2 unit and CLI smoke tests retained from the existing implementation."""

import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SOLUTION = Path(__file__).resolve().parents[2]
SRC = SOLUTION / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from common.domain import build_region_from_observations
from common.models import BearingObservation
from q1.geometry import contains
from q2.planner import Q2Config, plan_second_point


class Q2AlgorithmTestbench(unittest.TestCase):
    def setUp(self):
        self.source = (220.0, 280.0)
        self.sensor = (-600.0, -300.0)
        true = math.degrees(math.atan2(self.source[1]-self.sensor[1],
                                       self.source[0]-self.sensor[0])) % 360
        self.observation = BearingObservation(self.sensor, 1, "direction",
                                              true+0.6)

    def test_physical_region_is_bounded_and_contains_truth(self):
        region = build_region_from_observations([self.observation])
        self.assertEqual(region["status"], "bounded")
        self.assertTrue(contains(region["planes"], self.source))
        self.assertTrue(region["approximation"]["conservative"])

    def test_plan_is_deterministic_and_selected_from_candidates(self):
        first = plan_second_point(self.observation)
        second = plan_second_point(self.observation)
        self.assertEqual(first["selected_point"], second["selected_point"])
        self.assertIn(first["selected_point"], [
            first["baseline"]["selected_point"],
            first["continuous_fim"]["selected_point"],
        ])
        self.assertIn(first["baseline"]["selected_point"],
                      [item["point"] for item in first["candidates"]])
        self.assertEqual(first["selected_point"],
                         first[first["recommendation_source"]]["selected_point"])
        self.assertEqual(first["continuous_fim"]["status"], "ok")
        self.assertEqual(first["continuous_fim"]["selected_point"],
                         second["continuous_fim"]["selected_point"])
        self.assertAlmostEqual(
            first["continuous_fim"]["robust_fim_index_per_s"],
            second["continuous_fim"]["robust_fim_index_per_s"],
        )
        self.assertGreaterEqual(
            first["continuous_fim"]["robust_fim_index_per_s"] + 1e-15,
            first["continuous_fim"]["best_seed_fim_index_per_s"],
        )
        fim_selected = first["continuous_fim"]["selected"]
        self.assertTrue(fim_selected["guaranteed_reception"])
        self.assertAlmostEqual(
            fim_selected["score"],
            fim_selected["action_time_s"]
            + first["config"]["uncertainty_seconds_per_metre"]
            * fim_selected["worst_case_radius_m"],
        )
        self.assertAlmostEqual(
            first["comparison"]["continuous_minus_baseline"],
            fim_selected["score"] - first["baseline"]["selected"]["score"],
        )
        self.assertLessEqual(
            first["selected"]["worst_case_radius_m"],
            first["baseline"]["selected"]["worst_case_radius_m"] + 1e-9,
        )
        self.assertTrue(first["pareto_front"])
        for candidate in first["pareto_front"]:
            self.assertFalse(any(
                other["action_time_s"] <= candidate["action_time_s"] + 1e-9
                and other["worst_case_radius_m"]
                < candidate["worst_case_radius_m"] - 1e-9
                for other in first["pareto_front"]
            ))
        for solution in first["continuous_fim"]["budget_solutions"]:
            if solution["status"] == "ok":
                self.assertLessEqual(solution["action_time_s"],
                                     solution["max_action_time_s"] + 1e-8)
        for branch_name in ("baseline", "continuous_fim"):
            branch = first[branch_name]
            status = branch["near_optimal_region_meta"]["status"]
            self.assertIn(status, ("ok", "partial"))
            if status == "partial":
                self.assertTrue(branch["near_optimal_region_meta"]["timed_out"])
            self.assertEqual(set(branch["near_optimal_regions"]),
                             {"5pct", "10pct"})
            for near in branch["near_optimal_regions"].values():
                self.assertGreaterEqual(near["qualified_sample_count"], 1)
                for component in near["components"]:
                    for point in component["vertices"]:
                        self.assertTrue(_inside_convex(
                            first["candidate_regions"]
                            ["guaranteed_reception"]["vertices"],
                            point,
                        ))

    def test_selected_is_best_guaranteed_candidate_when_available(self):
        plan = plan_second_point(self.observation)
        guaranteed = [item for item in plan["candidates"]
                      if item["guaranteed_reception"]]
        self.assertTrue(guaranteed)
        expected = min(guaranteed, key=lambda item: (item["score"],
                       -item["fim_proxy_per_s"], item["point"]))
        self.assertEqual(plan["baseline"]["selected_point"], expected["point"])

    def test_continuous_candidate_regions_have_auditable_bounds(self):
        plan = plan_second_point(self.observation)
        regions = plan["candidate_regions"]
        guaranteed = regions["guaranteed_reception"]
        possible = regions["possible_reception"]
        self.assertEqual(guaranteed["status"], "bounded")
        self.assertEqual(possible["status"], "bounded")
        self.assertEqual(guaranteed["approximation"]["relation_to_exact_region"],
                         "inner")
        self.assertEqual(possible["approximation"]["relation_to_exact_region"],
                         "outer")
        for sensor in guaranteed["vertices"]:
            self.assertLessEqual(
                max(math.dist(sensor, source)
                    for source in plan["region"]["vertices"]),
                plan["config"]["min_receive_radius"]+1e-6,
            )
        for source in plan["region"]["vertices"]:
            self.assertTrue(_inside_convex(possible["vertices"], source))

    def test_no_guaranteed_candidate_falls_back_without_crash(self):
        plan = plan_second_point(
            self.observation,
            config=Q2Config(min_receive_radius=10.0, scenario_limit=6,
                            circle_sides=16),
        )
        self.assertEqual(plan["guaranteed_candidate_count"], 0)
        self.assertFalse(plan["selected"]["guaranteed_reception"])
        self.assertEqual(
            plan["candidate_regions"]["guaranteed_reception"]["status"],
            "empty",
        )
        self.assertEqual(plan["continuous_fim"]["status"], "unavailable")
        self.assertEqual(plan["continuous_fim"]["reason"],
                         "guaranteed_reception_region_empty")

    def test_non_direction_input_is_rejected(self):
        obs = BearingObservation(self.sensor, 1, "no_signal")
        with self.assertRaises(ValueError):
            plan_second_point(obs)

    def test_all_scores_are_finite_and_have_time_breakdown(self):
        plan = plan_second_point(self.observation)
        for item in plan["candidates"]:
            self.assertTrue(math.isfinite(item["score"]))
            self.assertGreaterEqual(item["action_time_s"], 5.0)
            self.assertGreaterEqual(item["worst_case_radius_m"], 0.0)
            self.assertAlmostEqual(item["action_time_s"],
                                   item["time_breakdown"]["total_s"])

    def test_selected_measurement_keeps_compatible_truth_and_contracts(self):
        plan = plan_second_point(self.observation)
        sensor = tuple(plan["selected_point"])
        true = math.degrees(math.atan2(self.source[1]-sensor[1],
                                       self.source[0]-sensor[0])) % 360
        second = BearingObservation(sensor, 1, "direction", true-0.7)
        posterior = build_region_from_observations([self.observation, second])
        self.assertTrue(contains(posterior["planes"], self.source))
        self.assertLessEqual(
            posterior["minimum_enclosing_circle"]["radius"],
            plan["region"]["minimum_enclosing_circle"]["radius"]+1e-7,
        )


class Q2CliTestbench(unittest.TestCase):
    def test_cli_writes_json_and_png(self):
        with tempfile.TemporaryDirectory() as directory:
            json_path = Path(directory) / "result.json"
            image_path = Path(directory) / "result.png"
            process = subprocess.run(
                [sys.executable, str(SRC/"q2"/"cli.py"), "--demo",
                 "--no-show", "--output", str(image_path),
                 "--result-json", str(json_path)],
                capture_output=True, text=True, timeout=60,
            )
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertGreater(image_path.stat().st_size, 10_000)
            data = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(data["method"],
                             "time_budgeted_fim_pareto_hybrid")
            self.assertEqual(len(data["selected_point"]), 2)
            self.assertIn("candidate_regions", data)
            self.assertEqual(data["continuous_fim"]["status"], "ok")
            self.assertIn("selected_score", data["continuous_fim"])
            self.assertIn("离散搜索基线", process.stdout)
            self.assertIn("连续FIM优化", process.stdout)
            self.assertIn("Pareto安全裁决", process.stdout)
            self.assertIn("near_optimal_regions", data["baseline"])
            self.assertIn("near_optimal_regions", data["continuous_fim"])
            self.assertTrue(data["candidates"][0]["candidate_id"].startswith("C"))


def _inside_convex(polygon, point, tolerance=1e-6):
    signs = []
    for first, second in zip(polygon, polygon[1:]+polygon[:1]):
        cross = ((second[0]-first[0])*(point[1]-first[1])
                 -(second[1]-first[1])*(point[0]-first[0]))
        if abs(cross) > tolerance:
            signs.append(cross > 0)
    return not signs or all(sign == signs[0] for sign in signs)


if __name__ == "__main__":
    unittest.main()
