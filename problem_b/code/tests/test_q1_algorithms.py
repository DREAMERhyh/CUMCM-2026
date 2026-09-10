"""Q1 acceptance testbench: geometry algorithms and mathematical claims."""

import math
from pathlib import Path
import random
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from geometry import (bearing_planes, contains, diameter_bruteforce,
                      diameter_calipers, hull, intersect_halfplanes, localize,
                      minimum_enclosing_circle)
from plot_cli import analyze_q1, DEMO_BEARINGS, DEMO_POINTS


class Q1AlgorithmTestbench(unittest.TestCase):
    def test_rotating_calipers_matches_all_pairs_on_random_hulls(self):
        rng = random.Random(20260910)
        for _ in range(2000):
            points = [(rng.uniform(-1800, 1800), rng.uniform(-1800, 1800))
                      for _ in range(rng.randint(3, 60))]
            polygon = hull(points)
            expected, _ = diameter_bruteforce(polygon)
            actual, pair = diameter_calipers(polygon)
            self.assertAlmostEqual(actual, expected, places=8)
            self.assertAlmostEqual(math.dist(*pair), actual, places=8)

    def test_rotating_calipers_handles_degenerate_polygons(self):
        self.assertEqual(diameter_calipers([]), (None, None))
        self.assertEqual(diameter_calipers([(2, 3)]), (0.0, [(2, 3), (2, 3)]))
        length, pair = diameter_calipers([(2, 3), (-2, 3), (0, 3)])
        self.assertEqual(length, 4)
        self.assertEqual(pair, [(-2, 3), (2, 3)])

    def test_minimum_enclosing_circle_triangle_counterexample(self):
        triangle = [(0, 0), (20, 0), (10, 10*math.sqrt(3))]
        region = intersect_halfplanes([
            (0, -1, 0),
            (-math.sqrt(3), 1, 0),
            (math.sqrt(3), 1, 20*math.sqrt(3)),
        ])
        self.assertEqual(region["status"], "bounded")
        self.assertAlmostEqual(region["diameter"], 20)
        self.assertFalse(region["diameter_circle"]["covers"])
        circle = minimum_enclosing_circle(triangle)
        self.assertAlmostEqual(circle["radius"], 20/math.sqrt(3), places=9)
        self.assertGreater(circle["radius"], region["diameter"]/2)

    def test_two_bearing_wedges_can_reject_diameter_circle(self):
        points = [(-343.62704417091254, -1246.0866734130507),
                  (-1212.0212182085875, 343.742388136116)]
        bearings = [75.06330664608899, 343.33994364807705]
        result = analyze_q1(points, bearings)["region"]
        self.assertEqual(result["status"], "bounded")
        self.assertEqual(len(result["vertices"]), 4)
        self.assertAlmostEqual(result["diameter"], 63.2503253173, places=7)
        self.assertFalse(result["diameter_circle"]["covers"])
        self.assertGreater(result["minimum_enclosing_circle"]["radius"],
                           result["diameter"]/2)

    def test_error_margin_expands_or_preserves_demo_region(self):
        nominal = analyze_q1(DEMO_POINTS, DEMO_BEARINGS, 1.0)["region"]
        margin = analyze_q1(DEMO_POINTS, DEMO_BEARINGS, 1.005)["region"]
        self.assertEqual(nominal["status"], "bounded")
        self.assertEqual(margin["status"], "bounded")
        self.assertGreaterEqual(margin["diameter"]+1e-8, nominal["diameter"])
        for point in nominal["vertices"]:
            self.assertTrue(contains(margin["planes"], point))

    def test_progress_uses_only_observations_and_contracts(self):
        analysis = analyze_q1(DEMO_POINTS, DEMO_BEARINGS)
        progress = analysis["progress"]
        self.assertEqual([item["status"] for item in progress],
                         ["unbounded", "bounded", "bounded"])
        self.assertGreaterEqual(progress[1]["diameter"]+1e-8,
                                progress[2]["diameter"])
        self.assertNotIn("source", analysis["inputs"])

    def test_invalid_error_bound_is_rejected(self):
        for error in (0, -1, 90, math.inf, math.nan):
            with self.assertRaises(ValueError):
                analyze_q1(DEMO_POINTS, DEMO_BEARINGS, error)
        with self.assertRaises(ValueError):
            bearing_planes((0, 0), 0, 0)


if __name__ == "__main__":
    unittest.main()
