import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

CODE = Path(__file__).resolve().parents[1]
if str(CODE) not in sys.path:
    sys.path.insert(0, str(CODE))

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
        self.assertIn(first["selected_point"],
                      [item["point"] for item in first["candidates"]])

    def test_selected_is_best_guaranteed_candidate_when_available(self):
        plan = plan_second_point(self.observation)
        guaranteed = [item for item in plan["candidates"]
                      if item["guaranteed_reception"]]
        self.assertTrue(guaranteed)
        expected = min(guaranteed, key=lambda item: (item["score"],
                       -item["fim_proxy_per_s"], item["point"]))
        self.assertEqual(plan["selected_point"], expected["point"])

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
                [sys.executable, str(CODE/"q2"/"cli.py"), "--demo",
                 "--no-show", "--output", str(image_path),
                 "--result-json", str(json_path)],
                capture_output=True, text=True, timeout=60,
            )
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertGreater(image_path.stat().st_size, 10_000)
            data = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(data["method"],
                             "set_worst_case_radius_per_action_time")
            self.assertEqual(len(data["selected_point"]), 2)
            self.assertIn("candidate_regions", data)
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
