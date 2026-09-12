"""A1 排除圆修剪 + A6 可行代表点口径的单元测试（夜间自主优化）。"""

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from common.models import BearingObservation
from q2.planner import Q2Config, score_candidates
from q3.policy import Q3Policy, Q3State, SourceTrack


class PruningUnitTestbench(unittest.TestCase):
    def test_pruning_flag_defaults_off(self):
        self.assertFalse(Q3Policy().use_no_signal_pruning)
        self.assertFalse(Q3Policy(scan_layout="ring7").use_no_signal_pruning)

    def test_refine_no_signal_appends_exclusion_circle_when_enabled(self):
        policy = Q3Policy(use_no_signal_pruning=True)
        state = Q3State()
        track = SourceTrack(5, observations=[BearingObservation(
            (0.0, 0.0), 5, "direction", 30.0)],
            region={"status": "bounded"})
        state.sources[5] = track
        action = type("A", (), {
            "position": (900.0, 100.0), "channel": 5})()
        response = {"measure_result": "no_signal"}
        policy._record_measurement(state, action, response, mode="refine")
        self.assertEqual(track.exclusion_circles,
                         [((900.0, 100.0), 1000.0)])
        self.assertEqual(track.region.get("exclusion_circles"),
                         [((900.0, 100.0), 1000.0)])

    def test_scan_no_signal_never_appends_when_enabled(self):
        policy = Q3Policy(use_no_signal_pruning=True)
        state = Q3State()
        track = SourceTrack(5)
        state.sources[5] = track
        action = type("A", (), {"position": (0.0, 0.0), "channel": 5})()
        response = {"measure_result": "no_signal"}
        policy._record_measurement(state, action, response, mode="scan")
        self.assertEqual(track.exclusion_circles, [])

    def test_pruning_disabled_appends_nothing(self):
        policy = Q3Policy()  # 默认关闭
        state = Q3State()
        track = SourceTrack(5)
        state.sources[5] = track
        action = type("A", (), {"position": (900.0, 100.0), "channel": 5})()
        policy._record_measurement(
            state, action, {"measure_result": "no_signal"}, mode="refine")
        self.assertEqual(track.exclusion_circles, [])

    def test_refine_direction_does_not_change_pruning(self):
        policy = Q3Policy(use_no_signal_pruning=True)
        state = Q3State()
        track = SourceTrack(5)
        state.sources[5] = track
        action = type("A", (), {"position": (300.0, 0.0), "channel": 5})()
        policy._record_measurement(
            state, action, {"measure_result": "direction",
                            "svd_deg": 10.0}, mode="refine")
        self.assertEqual(track.exclusion_circles, [])
        self.assertEqual(len(track.observations), 1)


class FeasibleScenarioTestbench(unittest.TestCase):
    """A6：排除圆内代表点剔除 + worst_radius 不增。"""

    def _region(self, exclusion_circles=()):
        observation = BearingObservation((-600.0, -300.0), 1, "direction",
                                         35.89)
        from common.domain import build_region_from_observations
        region = build_region_from_observations(
            [observation], error_deg=1.005, circle_sides=16)
        region["exclusion_circles"] = list(exclusion_circles)
        return region, observation

    def test_excluded_points_are_dropped_from_scenarios(self):
        region, observation = self._region()
        config = Q2Config()
        vertices = region["vertices"]
        # 排除圆盖住区域几何中心 → 代表点变少或半径不增。
        center = region["minimum_enclosing_circle"]["center"]
        region, observation = self._region(
            exclusion_circles=[(tuple(center), 1000.0)])
        self.assertIsNotNone(vertices)
        scores = score_candidates(
            region, [observation], [(0.0, 0.0)],
            observation.position, 1, 1, config)
        self.assertEqual(len(scores), 1)
        self.assertTrue(scores[0]["worst_case_radius_m"] >= 0.0)

    def test_pruned_radius_never_exceeds_unpruned(self):
        observation = BearingObservation((-600.0, -300.0), 1, "direction",
                                         35.89)
        from common.domain import build_region_from_observations
        plain = build_region_from_observations([observation],
                                               error_deg=1.005,
                                               circle_sides=16)
        center = plain["minimum_enclosing_circle"]["center"]
        pruned = build_region_from_observations([observation],
                                                error_deg=1.005,
                                                circle_sides=16)
        pruned["exclusion_circles"] = [(tuple(center), 500.0)]
        config = Q2Config()
        base = score_candidates(plain, [observation], [(0.0, 0.0)],
                                observation.position, 1, 1, config)[0]
        cut = score_candidates(pruned, [observation], [(0.0, 0.0)],
                               observation.position, 1, 1, config)[0]
        self.assertLessEqual(cut["worst_case_radius_m"],
                             base["worst_case_radius_m"] + 1e-9)

    def test_full_exclusion_falls_back_to_all_scenarios(self):
        observation = BearingObservation((-600.0, -300.0), 1, "direction",
                                         35.89)
        from common.domain import build_region_from_observations
        region = build_region_from_observations([observation],
                                                error_deg=1.005,
                                                circle_sides=16)
        # 排除圆覆盖整个可能区域（用超大半径）→ 全被排除 → 回退全场景。
        region["exclusion_circles"] = [((0.0, 0.0), 100000.0)]
        config = Q2Config()
        scores = score_candidates(region, [observation], [(0.0, 0.0)],
                                  observation.position, 1, 1, config)
        self.assertEqual(len(scores), 1)
        self.assertGreater(scores[0]["worst_case_radius_m"], 0.0)


class OptimalStopTestbench(unittest.TestCase):
    """A3：区域收缩到 40m 内时猜中心点清除的最优停止（默认关闭）。"""

    def _state_with_radius(self, radius):
        state = Q3State()
        track = SourceTrack(5, region={
            "status": "bounded",
            "minimum_enclosing_circle": {
                "center": (100.0, 100.0), "radius": radius,
            },
        })
        state.sources[5] = track
        return state, track

    def test_optimal_stop_default_on_after_night_promotion(self):
        # 2026-09-12 夜间晋级：use_optimal_stop 默认开启（120+300 局双池
        # 门1 全过、总虚拟时间中位 -3300s、无任何恶化局）。显式 False 仍可选。
        self.assertTrue(Q3Policy().use_optimal_stop)
        off_policy = Q3Policy(use_optimal_stop=False)
        self.assertFalse(off_policy.use_optimal_stop)
        self.assertEqual(Q3Policy().guess_clear_threshold_m, 40.0)

    def test_guess_clear_within_threshold(self):
        state, track = self._state_with_radius(30.0)
        policy = Q3Policy(use_optimal_stop=True)
        action = policy._resolve_action(state)
        self.assertEqual(action.kind, "clear")
        self.assertEqual(action.channel, 5)
        self.assertEqual(action.position, (100.0, 100.0))
        self.assertTrue(track.clear_guessed)

    def test_no_guess_beyond_threshold(self):
        state, _ = self._state_with_radius(80.0)
        policy = Q3Policy(use_optimal_stop=True)
        with patch("q3.policy.plan_measurement",
                   return_value={"selected_point": (50.0, 50.0),
                                 "recommendation_source": "baseline",
                                 "baseline": {"selected_point": (50.0, 50.0)}}):
            action = policy._resolve_action(state)
        self.assertEqual(action.kind, "measure")  # 走 refine
        self.assertEqual(state.pending_mode, "refine")

    def test_certified_clear_still_wins(self):
        state, track = self._state_with_radius(10.0)
        policy = Q3Policy(use_optimal_stop=True)
        action = policy._resolve_action(state)
        self.assertEqual(action.kind, "clear")
        self.assertEqual(state.pending_mode, "certified_clear")
        self.assertFalse(track.clear_guessed)

    def test_guessed_once_only(self):
        state, track = self._state_with_radius(30.0)
        policy = Q3Policy(use_optimal_stop=True)
        policy._resolve_action(state)  # 第一次 guess
        with patch("q3.policy.plan_measurement",
                   return_value={"selected_point": (50.0, 50.0),
                                 "recommendation_source": "baseline",
                                 "baseline": {"selected_point": (50.0, 50.0)}}):
            action = policy._resolve_action(state)
        self.assertEqual(action.kind, "measure")  # 第二次走 refine
        self.assertEqual(state.pending_mode, "refine")


if __name__ == "__main__":
    unittest.main()