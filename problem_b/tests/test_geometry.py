"""Analytic and invariant checks, with no third-party dependencies."""

import copy
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from legacy.environment import calculate, demo, generate, measure, validate_scene
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

    def test_bounded_result_independent_of_viewport(self):
        observations=calculate(demo())["observations"]
        small=localize(observations,[-1,-1,1,1])
        large=localize(observations,[-1e6,-1e6,1e6,1e6])
        self.assertAlmostEqual(small["diameter"],large["diameter"])
        self.assertEqual(small["display_polygon"],[])

    def test_translation_invariance(self):
        scene=demo(); initial=calculate(scene)
        for item in scene["sources"]+scene["detectors"]:
            item["x"]+=100;item["y"]-=150
        moved=calculate(scene)
        self.assertAlmostEqual(initial["region"]["diameter"],moved["region"]["diameter"],places=8)

    def test_synthetic_truth_and_monotonic_contraction(self):
        # 60 seeds, 8 observations each; no assumed official source distribution.
        for seed in range(60):
            scene=generate(dict(seed=seed,detector_count=8,mode="uniform"))
            full=calculate(scene)
            self.assertTrue(all(o["status"]=="direction" for o in full["observations"]))
            last=math.inf
            for count in range(1,9):
                current=dict(scene,detectors=scene["detectors"][:count])
                r=calculate(current)
                self.assertTrue(r["audit"]["truth_in_region"])
                if r["region"]["status"]=="bounded":
                    self.assertLessEqual(r["region"]["diameter"],last+1e-6)
                    last=r["region"]["diameter"]


class EnvironmentTests(unittest.TestCase):
    def test_cardinal_bearings(self):
        s=dict(x=0,y=0,radius=1000,channel=1)
        for x,y,expected in [(-100,0,0),(0,-100,90),(100,0,180),(0,100,270)]:
            self.assertEqual(measure(s,dict(x=x,y=y,error_deg=0),0)["bearing_deg"],expected)

    def test_fixed_error_same_location_and_channel(self):
        s=dict(x=0,y=0,radius=1000,channel=1);d=dict(x=100,y=200,error_deg=None)
        a=measure(s,d,2026);b=measure(s,dict(d),2026)
        self.assertEqual(a,b)
        self.assertLessEqual(abs(a["error_deg"]),1)

    def test_repeat_observation_does_not_shrink(self):
        s=demo();original=calculate(s)
        s["detectors"].append(copy.deepcopy(s["detectors"][0]))
        repeated=calculate(s)
        self.assertAlmostEqual(original["region"]["diameter"],repeated["region"]["diameter"])

    def test_conflicting_same_place_errors_rejected(self):
        s=demo();s["detectors"].append(dict(s["detectors"][0],error_deg=-1))
        with self.assertRaisesRegex(ValueError,"同一检测位置"):
            calculate(s)

    def test_valid_direction_input_contract(self):
        for x in (0,5,1250.0001):
            s=dict(seed=0,active_channel=1,sources=[dict(x=0,y=0,radius=1250,channel=1)],detectors=[dict(x=x,y=0,error_deg=0)])
            with self.assertRaisesRegex(ValueError,"无有效示向度"):
                calculate(s)
        s["detectors"][0]["x"]=1250
        self.assertEqual(calculate(s)["region"]["bearing_count"],1)

    def test_error_bound_endpoints(self):
        s=demo()
        for error in (-1,1):
            for detector in s["detectors"]:
                detector["error_deg"]=error
            self.assertTrue(calculate(s)["audit"]["truth_in_region"])

    def test_deterministic_generation_and_domain(self):
        for mode in ("nearby","uniform"):
            for seed in range(20):
                options=dict(seed=seed,source_count=3,detector_count=12,mode=mode)
                s=generate(options)
                self.assertEqual(s,generate(options))
                self.assertTrue(all(math.hypot(p["x"],p["y"])<=1800 for p in s["sources"]+s["detectors"]))
                self.assertEqual(calculate(s)["region"]["bearing_count"],12)

    def test_source_channel_and_finite_validation(self):
        s=demo();s["sources"].append(dict(s["sources"][0]))
        with self.assertRaisesRegex(ValueError,"不同频道"):
            validate_scene(s)
        s=demo();s["detectors"][0]["x"]=float("nan")
        with self.assertRaises(ValueError):
            validate_scene(s)

    def test_outside_domain_detector_can_still_be_valid(self):
        s=dict(seed=0,active_channel=1,sources=[dict(x=1700,y=0,radius=1000,channel=1)],detectors=[dict(x=2000,y=0,error_deg=0)])
        self.assertEqual(calculate(s)["region"]["bearing_count"],1)

    def test_solver_does_not_require_truth(self):
        r=calculate(demo())
        public=[{k:o[k] for k in ("position","status","bearing_deg")} for o in r["observations"]]
        self.assertEqual(localize(public,r["bounds"])["vertices"],r["region"]["vertices"])


if __name__ == "__main__":
    unittest.main()
