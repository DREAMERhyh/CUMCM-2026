"""Regression checks for the legacy synthetic browser environment."""

import copy
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from legacy.environment import calculate, demo, generate, measure, validate_scene
from q1.geometry import localize


class EnvironmentTests(unittest.TestCase):
    def test_bounded_result_independent_of_viewport(self):
        observations = calculate(demo())["observations"]
        small = localize(observations, [-1, -1, 1, 1])
        large = localize(observations, [-1e6, -1e6, 1e6, 1e6])
        self.assertAlmostEqual(small["diameter"], large["diameter"])
        self.assertEqual(small["display_polygon"], [])

    def test_translation_invariance(self):
        scene = demo()
        initial = calculate(scene)
        for item in scene["sources"] + scene["detectors"]:
            item["x"] += 100
            item["y"] -= 150
        moved = calculate(scene)
        self.assertAlmostEqual(initial["region"]["diameter"],
                               moved["region"]["diameter"], places=8)

    def test_synthetic_truth_and_monotonic_contraction(self):
        for seed in range(60):
            scene = generate(dict(seed=seed, detector_count=8, mode="uniform"))
            full = calculate(scene)
            self.assertTrue(all(o["status"] == "direction"
                                for o in full["observations"]))
            last = math.inf
            for count in range(1, 9):
                current = dict(scene, detectors=scene["detectors"][:count])
                result = calculate(current)
                self.assertTrue(result["audit"]["truth_in_region"])
                if result["region"]["status"] == "bounded":
                    self.assertLessEqual(result["region"]["diameter"],
                                         last + 1e-6)
                    last = result["region"]["diameter"]

    def test_cardinal_bearings(self):
        source = dict(x=0, y=0, radius=1000, channel=1)
        for x, y, expected in [(-100, 0, 0), (0, -100, 90),
                               (100, 0, 180), (0, 100, 270)]:
            self.assertEqual(measure(source, dict(x=x, y=y, error_deg=0), 0)
                             ["bearing_deg"], expected)

    def test_fixed_error_same_location_and_channel(self):
        source = dict(x=0, y=0, radius=1000, channel=1)
        detector = dict(x=100, y=200, error_deg=None)
        first = measure(source, detector, 2026)
        second = measure(source, dict(detector), 2026)
        self.assertEqual(first, second)
        self.assertLessEqual(abs(first["error_deg"]), 1)

    def test_repeat_observation_does_not_shrink(self):
        scene = demo()
        original = calculate(scene)
        scene["detectors"].append(copy.deepcopy(scene["detectors"][0]))
        repeated = calculate(scene)
        self.assertAlmostEqual(original["region"]["diameter"],
                               repeated["region"]["diameter"])

    def test_conflicting_same_place_errors_rejected(self):
        scene = demo()
        scene["detectors"].append(dict(scene["detectors"][0], error_deg=-1))
        with self.assertRaisesRegex(ValueError, "同一检测位置"):
            calculate(scene)

    def test_valid_direction_input_contract(self):
        for x in (0, 5, 1250.0001):
            scene = dict(
                seed=0,
                active_channel=1,
                sources=[dict(x=0, y=0, radius=1250, channel=1)],
                detectors=[dict(x=x, y=0, error_deg=0)],
            )
            with self.assertRaisesRegex(ValueError, "无有效示向度"):
                calculate(scene)
        scene["detectors"][0]["x"] = 1250
        self.assertEqual(calculate(scene)["region"]["bearing_count"], 1)

    def test_error_bound_endpoints(self):
        scene = demo()
        for error in (-1, 1):
            for detector in scene["detectors"]:
                detector["error_deg"] = error
            self.assertTrue(calculate(scene)["audit"]["truth_in_region"])

    def test_deterministic_generation_and_domain(self):
        for mode in ("nearby", "uniform"):
            for seed in range(20):
                options = dict(seed=seed, source_count=3,
                               detector_count=12, mode=mode)
                scene = generate(options)
                self.assertEqual(scene, generate(options))
                self.assertTrue(all(math.hypot(p["x"], p["y"]) <= 1800
                                    for p in scene["sources"] + scene["detectors"]))
                self.assertEqual(calculate(scene)["region"]["bearing_count"], 12)

    def test_source_channel_and_finite_validation(self):
        scene = demo()
        scene["sources"].append(dict(scene["sources"][0]))
        with self.assertRaisesRegex(ValueError, "不同频道"):
            validate_scene(scene)
        scene = demo()
        scene["detectors"][0]["x"] = float("nan")
        with self.assertRaises(ValueError):
            validate_scene(scene)

    def test_outside_domain_detector_can_still_be_valid(self):
        scene = dict(
            seed=0,
            active_channel=1,
            sources=[dict(x=1700, y=0, radius=1000, channel=1)],
            detectors=[dict(x=2000, y=0, error_deg=0)],
        )
        self.assertEqual(calculate(scene)["region"]["bearing_count"], 1)

    def test_solver_does_not_require_truth(self):
        result = calculate(demo())
        public = [{key: observation[key]
                   for key in ("position", "status", "bearing_deg")}
                  for observation in result["observations"]]
        self.assertEqual(localize(public, result["bounds"])["vertices"],
                         result["region"]["vertices"])


if __name__ == "__main__":
    unittest.main()
