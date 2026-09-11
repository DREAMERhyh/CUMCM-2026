"""Q1 unit tests: analytic geometry and invariants."""

import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from q1.geometry import (bearing_planes, contains, diameter,
                         intersect_halfplanes, localize)


class GeometryTests(unittest.TestCase):
    def test_rectangle_analytic_diameter(self):
        r = intersect_halfplanes([(1,0,4),(-1,0,0),(0,1,3),(0,-1,0)])
        self.assertEqual(r["status"], "bounded")
        self.assertEqual(len(r["vertices"]), 4)
        self.assertAlmostEqual(r["diameter"], 5)
        self.assertAlmostEqual(r["area"], 12)
        self.assertTrue(r["diameter_circle"]["covers"])

    def test_triangle_diameter_circle_does_not_cover(self):
        r = intersect_halfplanes([(0,-1,0),(-math.sqrt(3),1,0),(math.sqrt(3),1,20*math.sqrt(3))])
        self.assertAlmostEqual(r["diameter"],20)
        self.assertFalse(r["diameter_circle"]["covers"])

    def test_longest_pair_can_be_edge(self):
        d, pair = diameter([(0,0),(10,0),(9,.1),(1,.1)])
        self.assertEqual(d,10)
        self.assertEqual(pair,[(0,0),(10,0)])

    def test_empty(self):
        self.assertEqual(intersect_halfplanes([(1,0,0),(-1,0,-1)])["status"],"empty")

    def test_single_point(self):
        r = intersect_halfplanes([(1,0,2),(-1,0,-2),(0,1,3),(0,-1,-3)])
        self.assertEqual(r["vertices"],[(2,3)])
        self.assertEqual(r["diameter"],0)

    def test_line_segment(self):
        r = intersect_halfplanes([(1,0,2),(-1,0,2),(0,1,3),(0,-1,-3)])
        self.assertEqual(len(r["vertices"]),2)
        self.assertEqual(r["diameter"],4)

    def test_unbounded_region_never_uses_viewport_diameter(self):
        obs=[dict(position=[0,0],status="direction",bearing_deg=45)]
        for extent in (10,2100,1e6):
            r=localize(obs,[-extent,-extent,extent,extent])
            self.assertEqual(r["status"],"unbounded")
            self.assertIsNone(r["diameter"])
            self.assertGreater(len(r["display_polygon"]),2)

    def test_parallel_strip_is_unbounded(self):
        self.assertEqual(intersect_halfplanes([(1,0,3),(-1,0,-2)])["status"],"unbounded")

    def test_wraparound_and_forward_ray(self):
        planes=bearing_planes((0,0),359.8)
        self.assertTrue(contains(planes,(1000,0)))
        self.assertFalse(contains(planes,(-1000,0)))
        self.assertTrue(contains(bearing_planes((0,0),0),(1000,0)))

if __name__ == "__main__":
    unittest.main()
