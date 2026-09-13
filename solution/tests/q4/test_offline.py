"""Q4 geometry, belief, rolling-gate and offline policy checks."""

import json
import math
from pathlib import Path
import random
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from common.domain import build_region_from_observations
from common.models import BearingObservation
from q1.geometry import contains
from q3.adaptive import nearest_neighbor_order
from q3.policy import SourceTrack
from q3.route import RouteEstimate, RoutePlan
from q4.belief import Q4Measurement, build_joint_belief
from q4.directional import (adaptive_four_sided_points,
                            certified_probe_points, four_sided_points,
                            grid121, is_visible, triangular_scan_mesh,
                            triangular25, triangular37)
from q4.policy import Q4Policy
from runtime.runner import run_policy
from sim.fake import FakeSimulator, FakeSource


class Q4TheoryTestbench(unittest.TestCase):
    def test_grid121_covers_random_positions_and_directions(self):
        rng = random.Random(20260911)
        grid = grid121()
        self.assertEqual(len(grid), 121)
        for _ in range(3000):
            radius = 1800*math.sqrt(rng.random())
            angle = 2*math.pi*rng.random()
            source = (radius*math.cos(angle), radius*math.sin(angle))
            direction = 360*rng.random()
            self.assertTrue(any(is_visible(source, direction, sensor)
                                for sensor in grid))

    def test_four_sided_certificate_and_rejection_boundary(self):
        self.assertEqual(len(four_sided_points((10.0, -20.0), 100.0)), 4)
        self.assertEqual(four_sided_points((0.0, 0.0), 150.0), [])
        self.assertEqual(four_sided_points((0.0, 0.0), 850.0), [])

    def test_four_sided_points_have_a_visible_member(self):
        center, radius = (20.0, -30.0), 100.0
        probes = four_sided_points(center, radius)
        for direction in range(0, 360, 5):
            angle = math.radians(direction)
            source = (center[0]+radius*math.cos(angle+1.1),
                      center[1]+radius*math.sin(angle+1.1))
            self.assertTrue(any(is_visible(source, direction, point)
                                for point in probes))

    def test_adaptive_four_sided_certificate_extends_to_300_m_radius(self):
        center, radius = (20.0, -30.0), 300.0
        probes = adaptive_four_sided_points(center, radius)
        self.assertEqual(len(probes), 4)
        rho = math.dist(center, probes[0])
        self.assertGreater(rho/math.sqrt(2.0), radius)
        self.assertLessEqual(rho+radius, 1000.0+1e-9)
        for source_angle in range(0, 360, 10):
            angle = math.radians(source_angle)
            source = (
                center[0]+radius*math.cos(angle),
                center[1]+radius*math.sin(angle),
            )
            for direction in range(0, 360, 5):
                self.assertTrue(any(
                    is_visible(source, direction, point)
                    for point in probes
                ))
        self.assertEqual(
            adaptive_four_sided_points(center, 415.0), [],
        )

    def test_triangular37_has_structural_and_dense_coverage(self):
        points, triangles = triangular_scan_mesh()
        self.assertEqual(points, triangular37())
        self.assertEqual(len(points), 37)
        path_length = sum(
            math.dist(first, second)
            for first, second in zip(points, points[1:])
        )
        self.assertAlmostEqual(path_length, 36*900.0, places=6)
        self.assertTrue(all(
            math.dist(first, second) <= 900.0+1e-7
            for first, second in zip(points, points[1:])
        ))
        self.assertTrue(triangles)
        point_set = set(points)
        for triangle in triangles:
            self.assertTrue(set(triangle) <= point_set)
            for first, second in zip(triangle, triangle[1:]+triangle[:1]):
                self.assertLessEqual(math.dist(first, second), 900.0+1e-7)
        for radial_index in range(31):
            radius = 1800.0*radial_index/30.0
            for source_angle in range(0, 360, 3):
                angle = math.radians(source_angle)
                source = (radius*math.cos(angle), radius*math.sin(angle))
                for direction in range(0, 360, 15):
                    self.assertTrue(any(
                        is_visible(source, direction, point)
                        for point in points
                    ))

    def test_triangular25_has_structural_and_dense_coverage(self):
        points, triangles = triangular_scan_mesh(
            spacing=985.0, lattice_phase=(0.112, 0.112),
        )
        self.assertEqual(points, triangular25())
        self.assertEqual(len(points), 25)
        self.assertNotIn((0.0, 0.0), points)
        path_length = math.dist((0.0, 0.0), points[0])+sum(
            math.dist(first, second)
            for first, second in zip(points, points[1:])
        )
        self.assertAlmostEqual(path_length, 24552.14989054634, places=6)
        self.assertTrue(triangles)
        point_set = set(points)
        for triangle in triangles:
            self.assertTrue(set(triangle) <= point_set)
            for first, second in zip(triangle, triangle[1:]+triangle[:1]):
                self.assertLessEqual(math.dist(first, second), 985.0+1e-7)
        for radial_index in range(61):
            radius = 1800.0*radial_index/60.0
            for source_angle in range(0, 360, 2):
                angle = math.radians(source_angle)
                source = (radius*math.cos(angle), radius*math.sin(angle))
                for direction in range(0, 360, 15):
                    self.assertTrue(any(
                        is_visible(source, direction, point)
                        for point in points
                    ))

    def test_probe_bundle_is_not_cut_off_by_individual_measure_limit(self):
        policy = Q4Policy(
            max_refinements=1, directional_rolling_mode="off",
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
        for index in range(4):
            action = policy.next_action(state)
            self.assertEqual(action.kind, "measure")
            self.assertEqual(action.channel, 7)
            attempted.append(tuple(action.position))
            response = {
                "accepted": True,
                "virtual_time_s": float(index+1),
                "measure_result": "near" if index == 3 else "no_signal",
            }
            policy.apply_response(state, action, response)
        self.assertEqual(len(set(attempted)), 4)
        self.assertEqual(state.forced_clear[1], 7)
        self.assertEqual(state.probe_bundle_counts[7], 1)

    def test_large_posterior_gets_triangular_direction_certificate(self):
        observation = BearingObservation(
            (900.0, 0.0), 7, "direction", 180.0,
        )
        region = build_region_from_observations(
            [observation], error_deg=1.005, circle_sides=16,
        )
        self.assertGreater(
            region["minimum_enclosing_circle"]["radius"], 414.2,
        )
        probes, kind = certified_probe_points(region)
        self.assertEqual(kind, "triangular_local")
        self.assertGreater(len(probes), 4)
        samples = [
            tuple(region["minimum_enclosing_circle"]["center"]),
            *[tuple(point) for point in region["vertices"]],
        ]
        xs = [point[0] for point in region["vertices"]]
        ys = [point[1] for point in region["vertices"]]
        for iy in range(21):
            y = min(ys)+(max(ys)-min(ys))*iy/20.0
            for ix in range(21):
                x = min(xs)+(max(xs)-min(xs))*ix/20.0
                if contains(region["planes"], (x, y)):
                    samples.append((x, y))
        for source in samples:
            for direction in range(0, 360, 10):
                self.assertTrue(any(
                    is_visible(source, direction, point)
                    for point in probes
                ))

    def test_default_directional_rolling_selects_certified_probe(self):
        policy = Q4Policy(max_refinements=1)
        state = policy.initial_state()
        state.entered = True
        state.phase = "resolve"
        observation = BearingObservation(
            (900.0, 0.0), 7, "direction", 180.0,
        )
        region = build_region_from_observations(
            [observation], error_deg=policy.error_deg, circle_sides=16,
        )
        track = SourceTrack(7, observations=[observation], region=region)
        state.sources[7] = track
        state.position = observation.position
        state.current_channel = 7
        state.measure_history[7] = [
            Q4Measurement(
                observation.position, "direction", observation.bearing_deg,
            )
        ]
        policy._refresh_belief(state, track)
        action = policy.next_action(state)
        self.assertEqual(action.kind, "measure")
        self.assertEqual(state.pending_mode, "directional_probe")
        self.assertEqual(track.last_rolling_decision["decision"], "measure")
        self.assertEqual(
            state.probe_bundles[7].kind, "triangular_local",
        )

    def test_failed_clear_gate_can_remeasure_without_moving(self):
        policy = Q4Policy(
            max_refinements=0,
            failed_clear_remeasure_mode="gated",
        )
        client = FakeSimulator([
            FakeSource(7, (1700.0, 0.0), 1000.0, direction_deg=0.0)
        ])
        state = policy.initial_state()
        failed_position = None
        found_remeasure = False
        for _ in range(4000):
            action = policy.next_action(state)
            mode = state.pending_mode
            if mode == "fallback_remeasure":
                self.assertEqual(tuple(action.position), failed_position)
                found_remeasure = True
                break
            response = client.execute(action)
            policy.apply_response(state, action, response)
            if (action.kind == "clear"
                    and response.get("clear_result")
                    == "no_target_in_range"):
                failed_position = tuple(action.position)
        self.assertTrue(found_remeasure)

    def test_regular_directional_rolling_keeps_bundle_horizon(self):
        policy = Q4Policy(long_clear_tail_mode="adaptive")
        state = policy.initial_state()
        observation = BearingObservation(
            (900.0, 0.0), 7, "direction", 180.0,
        )
        region = build_region_from_observations(
            [observation], error_deg=policy.error_deg, circle_sides=16,
        )
        track = SourceTrack(7, observations=[observation], region=region)
        state.sources[7] = track
        state.measure_history[7] = [
            Q4Measurement(observation.position, "direction", 180.0),
        ]
        policy._refresh_belief(state, track)
        with patch(
            "q4.policy.evaluate_directional_probe_decision",
            return_value={"decision": "clear", "reason": "test"},
        ) as evaluate:
            policy._evaluate_probe_decision(state, track, [(0.0, 0.0)])
        self.assertFalse(evaluate.call_args.kwargs["one_step_replan"])

    def test_long_clear_rescue_reopens_a_moving_probe_once(self):
        policy = Q4Policy(
            max_refinements=2, long_clear_tail_mode="adaptive",
            long_clear_rescue_failure_threshold=3,
        )
        state = policy.initial_state()
        observation = BearingObservation(
            (900.0, 0.0), 7, "direction", 180.0,
        )
        region = build_region_from_observations(
            [observation], error_deg=policy.error_deg, circle_sides=16,
        )
        track = SourceTrack(7, observations=[observation], region=region)
        track.refinement_stopped = True
        track.failed_clear_points = [(0.0, 0.0)]*3
        track.fallback_points = [(27.0, 0.0), (54.0, 0.0)]
        state.sources[7] = track
        decision = {
            "decision": "measure", "selected_point": (100.0, 100.0),
            "reason": "test",
        }
        with (patch.object(
                  policy, "_probe_points",
                  return_value=([(100.0, 100.0), (200.0, 100.0)], "test"),
              ), patch.object(
                  policy, "_rolling_probe_decision", return_value=decision,
              ) as rolling):
            action = policy._long_clear_rescue_action(state, track)
        self.assertEqual(action.kind, "measure")
        self.assertEqual(action.position, (100.0, 100.0))
        self.assertFalse(track.refinement_stopped)
        self.assertEqual(state.long_clear_rescue_counts[7], 1)
        self.assertTrue(rolling.call_args.kwargs["one_step_replan"])
        self.assertEqual(rolling.call_args.kwargs["risk_metric"], "mean")

    def test_observed_long_tail_replay_triggers_one_bounded_rescue(self):
        log_path = (
            Path(__file__).resolve().parents[2]
            / "output" / "sim" / "q4_20260912-225859-514262.jsonl"
        )
        if not log_path.exists():
            self.skipTest("观察到的Q4长尾日志不在当前工作区。")
        records = []
        for line in log_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            if record["sequence"] <= 404:
                records.append(record)
        direction_record = next(
            item for item in records
            if (item["action"]["kind"] == "measure"
                and item["action"]["channel"] == 9
                and item["response"].get("measure_result") == "direction")
        )
        failed_clears = [
            item for item in records
            if (item["action"]["kind"] == "clear"
                and item["action"]["channel"] == 9
                and item["response"].get("clear_result")
                == "no_target_in_range")
        ]
        no_signals = [
            item for item in records
            if (item["action"]["kind"] == "measure"
                and item["action"]["channel"] == 9
                and item["response"].get("measure_result") == "no_signal"
                and item["sequence"] > direction_record["sequence"])
        ]
        predecessor = next(
            item for item in records if item["sequence"] == 393
        )

        def restored_state(policy):
            point = direction_record["action"]["position"]
            observation = BearingObservation(
                (point["x"], point["y"]), 9, "direction",
                direction_record["response"]["svd_deg"],
            )
            region = build_region_from_observations(
                [observation], error_deg=policy.error_deg,
                circle_sides=16, q2_version=policy.q2_config.q2_version,
            )
            track = SourceTrack(
                9, observations=[observation], region=region,
            )
            start = predecessor["action"]["position"]
            start = (start["x"], start["y"])
            track.fallback_points = nearest_neighbor_order(
                policy._cached_posterior_clear_points(region), start,
            )
            failed_points = [
                (item["action"]["position"]["x"],
                 item["action"]["position"]["y"])
                for item in failed_clears
            ]
            self.assertEqual(track.fallback_points[:8], failed_points)
            track.fallback_index = len(failed_points)
            track.failed_clear_points = list(failed_points)
            track.failed_clear_disks = [
                (point, 20.0) for point in failed_points
            ]
            track.fallback_remeasure_count = len(no_signals)
            track.fallback_remeasure_points = [
                (item["action"]["position"]["x"],
                 item["action"]["position"]["y"])
                for item in no_signals
            ]
            track.fallback_remeasure_pending = True
            track.refinement_stopped = True
            state = policy.initial_state()
            state.entered = True
            state.phase = "resolve"
            state.position = failed_points[-1]
            state.current_channel = 9
            state.sources[9] = track
            state.measure_history[9] = [
                Q4Measurement(
                    observation.position, "direction",
                    observation.bearing_deg,
                ),
                *[
                    Q4Measurement(point, "no_signal")
                    for point in track.fallback_remeasure_points
                ],
            ]
            policy._refresh_belief(state, track)
            return state

        baseline = Q4Policy(long_clear_tail_mode="off")
        baseline_state = restored_state(baseline)
        baseline_next = baseline.next_action(baseline_state)
        self.assertEqual(baseline_next.kind, "clear")
        self.assertEqual(baseline_next.channel, 9)

        rescued = Q4Policy(long_clear_tail_mode="adaptive")
        rescued_state = restored_state(rescued)
        rescued_next = rescued.next_action(rescued_state)
        self.assertEqual(rescued_next.kind, "measure")
        self.assertEqual(rescued_next.channel, 9)
        self.assertNotEqual(rescued_next.position, baseline_next.position)
        started = [
            item for item in rescued_state.long_clear_diagnostics
            if item.get("event") == "long_clear_rescue_started"
        ]
        self.assertEqual(len(started), 1)
        self.assertGreater(
            started[0]["decision"]["estimated_saving_s"], 0.0,
        )

    def test_q4_route_commits_selected_directional_service(self):
        policy = Q4Policy(
            multi_source_route_mode="insertion_2opt",
            long_clear_tail_mode="off",
        )
        state = policy.initial_state()
        state.entered = True
        state.phase = "resolve"
        observation = BearingObservation(
            (900.0, 0.0), 7, "direction", 180.0,
        )
        region = build_region_from_observations(
            [observation], error_deg=policy.error_deg, circle_sides=16,
        )
        track = SourceTrack(7, observations=[observation], region=region)
        state.sources[7] = track
        state.measure_history[7] = [
            Q4Measurement(observation.position, "direction", 180.0),
        ]
        policy._refresh_belief(state, track)
        estimate = RouteEstimate(
            order=(7,), blocks=(), total_virtual_time_s=100.0,
            total_movement_distance_m=100.0, long_jump_count=0,
            long_jump_distance_m=0.0, end_position=(0.0, 0.0),
            end_channel=7,
        )
        route_plan = RoutePlan(
            status="ok", reason="complete", estimate=estimate,
            insertion_order=(7,), two_opt_iterations=0,
            cpu_wall_time_s=0.01,
        )
        with patch("q4.policy.plan_service_route", return_value=route_plan):
            action = policy.next_action(state)
        self.assertEqual(action.channel, 7)
        self.assertIn(action.kind, ("measure", "clear"))
        self.assertEqual(policy.route_planning_history[-1]["order"], [7])
        self.assertEqual(state.route_active_channel, 7)
        state.route_active_channel = None
        fallback_action = SimpleNamespace(channel=7)
        with (patch("q4.policy.plan_service_route", return_value=None),
              patch.object(
                  policy, "_legacy_resolve_choice",
                  return_value=fallback_action,
              )):
            selected = policy._q4_route_resolve_choice(state, [7])
        self.assertIs(selected, fallback_action)
        self.assertEqual(state.route_active_channel, 7)

    def test_joint_belief_uses_no_signal_to_reject_omni_scenarios(self):
        observations = [
            BearingObservation((500.0, 0.0), 7, "direction", 180.0),
            BearingObservation((0.0, 500.0), 7, "direction", 270.0),
            BearingObservation((0.0, -500.0), 7, "direction", 90.0),
        ]
        region = build_region_from_observations(
            observations, error_deg=1.005, circle_sides=16,
        )
        history = [
            Q4Measurement(item.position, "direction", item.bearing_deg)
            for item in observations
        ]
        history.append(Q4Measurement((-500.0, 0.0), "no_signal"))
        belief = build_joint_belief(region, history)
        summary = belief.summary()
        self.assertEqual(summary["status"], "ok")
        self.assertGreater(summary["scenario_count"], 0)
        self.assertAlmostEqual(summary["omni_weight"], 0.0)
        self.assertAlmostEqual(summary["directional_weight"], 1.0)
        self.assertTrue(all(
            item.source_kind == "directional"
            for item in belief.scenarios
        ))
        one_position = build_joint_belief(
            region, history, position_limit=1,
        )
        self.assertEqual(one_position.position_sample_count, 1)

    def test_q4_policy_finitely_clears_directional_source_offline(self):
        client = FakeSimulator([
            FakeSource(7, (1700.0, 0.0), 1000.0, direction_deg=0.0)
        ])
        summary = run_policy(Q4Policy(max_refinements=0), client,
                             max_actions=4000)
        self.assertEqual(summary.cleared_channels, [7])
        self.assertEqual(len(summary.absent_channels), 19)
        self.assertEqual(summary.exit_reason, "user_exit")
        self.assertLess(len(summary.actions), 4000)

    def test_q4_defaults_keep_q3_route_off_and_use_safe_q4_features(self):
        policy = Q4Policy()
        self.assertEqual(policy.scan_mode, "triangular25")
        self.assertEqual(len(policy.coverage_points), 25)
        self.assertTrue(policy.posterior_grid)
        self.assertEqual(policy.joint_batch_mode, "off")
        self.assertEqual(policy.failed_clear_remeasure_mode, "gated")
        self.assertEqual(policy.rolling_time_mode, "off")
        self.assertEqual(policy.directional_rolling_mode, "scenario")
        self.assertEqual(policy.long_clear_tail_mode, "adaptive")
        self.assertEqual(
            policy.directional_rolling_cpu_time_limit_s, 3.0,
        )
        self.assertEqual(policy.multi_source_route_mode, "off")
        self.assertEqual(policy.q2_config.q2_version, "new")
        legacy = Q4Policy(q2_version="legacy")
        self.assertEqual(legacy.q2_config.q2_version, "legacy")


if __name__ == "__main__":
    unittest.main()
