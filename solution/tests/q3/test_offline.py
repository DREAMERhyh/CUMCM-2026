"""Offline theory and state-machine checks for the current Q3 strategy."""

import math
from pathlib import Path
import random
import sys
import unittest
from unittest.mock import patch

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from common.models import Action, BearingObservation
from q1.geometry import intersect_halfplanes
from q3.adaptive import (CLEAR_RADIUS_M, DEFAULT_CLEAR_GRID_SPACING_M,
                         measurement_is_worthwhile,
                         posterior_clear_points)
from q3.coverage import nearest_coverage_distance, ring7, strip_clear_points
from q3.cache import Q3ComputationCache
from q3.fallback_remeasure import evaluate_failed_clear_remeasure
from q3.policy import Q3Policy, Q3State, SourceTrack
from q3.route import (RouteEstimate, RoutePlan, SourceServiceSpec,
                      cheapest_insertion, evaluate_open_service_route,
                      improve_two_opt, materialize_service_block,
                      plan_beam_cached_route, plan_service_route)
from q3.rolling_time import (clear_plan_cost, evaluate_candidate,
                             evaluate_total_time_decision, risk_summary)
from q4.policy import Q4Policy
from runtime.runner import run_policy
from sim.fake import FakeSimulator, FakeSource
from sim.protocol import build_request_payload


class Q3TheoryTestbench(unittest.TestCase):
    @staticmethod
    def _small_region(radius=100.0):
        planes = [
            (1.0, 0.0, radius), (-1.0, 0.0, radius),
            (0.0, 1.0, radius), (0.0, -1.0, radius),
        ]
        region = intersect_halfplanes(planes)
        region["planes"] = planes
        return region

    @staticmethod
    def _rolling_candidate_result(point, action_s, p90_s, mean_s=None):
        mean_s = p90_s if mean_s is None else mean_s
        return {
            "point": tuple(point),
            "measure_action_time_s": action_s,
            "measure_time_breakdown": {},
            "post_clear_mean_s": mean_s,
            "post_clear_p90_s": p90_s,
            "post_clear_cvar_s": p90_s,
            "post_clear_worst_s": p90_s,
            "mean_clear_point_count": 3.0,
            "scenario_count": 12,
        }

    @staticmethod
    def _certified_spec(channel, point):
        return SourceServiceSpec(
            channel=channel,
            mode="certified_clear",
            entry_point=tuple(point),
            entry_action_kind="clear",
            entry_action_channel=channel,
            route_points=(tuple(point),),
            source_version=(channel,),
        )

    def test_open_route_cost_counts_movement_and_clear_actions(self):
        specs = {
            1: self._certified_spec(1, (0.0, 0.0)),
            2: self._certified_spec(2, (50.0, 0.0)),
            3: self._certified_spec(3, (100.0, 0.0)),
        }
        route = evaluate_open_service_route(
            (1, 2, 3), specs, (0.0, 0.0), 1
        )
        self.assertAlmostEqual(route.total_movement_distance_m, 100.0)
        self.assertAlmostEqual(route.total_virtual_time_s, 35.0)
        self.assertEqual(route.end_position, (100.0, 0.0))

    def test_cheapest_insertion_beats_channel_order(self):
        specs = {
            1: self._certified_spec(1, (1000.0, 0.0)),
            2: self._certified_spec(2, (10.0, 0.0)),
            3: self._certified_spec(3, (20.0, 0.0)),
        }
        channel_order = evaluate_open_service_route(
            (1, 2, 3), specs, (0.0, 0.0), 1
        )
        route = cheapest_insertion(specs, (0.0, 0.0), 1)
        self.assertEqual(route.order, (2, 3, 1))
        self.assertLess(route.total_virtual_time_s,
                        channel_order.total_virtual_time_s)

    def test_two_opt_strictly_improves_folded_open_route(self):
        specs = {
            1: self._certified_spec(1, (0.0, 100.0)),
            2: self._certified_spec(2, (100.0, 0.0)),
            3: self._certified_spec(3, (100.0, 100.0)),
            4: self._certified_spec(4, (200.0, 0.0)),
        }
        initial = evaluate_open_service_route(
            (1, 2, 3, 4), specs, (0.0, 0.0), 1
        )
        improved, iterations, timed_out = improve_two_opt(
            initial, specs, (0.0, 0.0), 1
        )
        self.assertGreaterEqual(iterations, 1)
        self.assertFalse(timed_out)
        self.assertLess(improved.total_virtual_time_s,
                        initial.total_virtual_time_s)

    def test_route_planning_is_deterministic(self):
        specs = {
            channel: self._certified_spec(channel, point)
            for channel, point in {
                1: (100.0, 100.0), 2: (-100.0, 100.0),
                3: (-100.0, -100.0), 4: (100.0, -100.0),
            }.items()
        }
        first = plan_service_route(
            specs, (0.0, 0.0), 1, cpu_time_limit_s=1.0
        )
        second = plan_service_route(
            specs, (0.0, 0.0), 1, cpu_time_limit_s=1.0
        )
        self.assertEqual(first.status, "ok")
        self.assertEqual(first.estimate.order, second.estimate.order)
        self.assertAlmostEqual(first.estimate.total_virtual_time_s,
                               second.estimate.total_virtual_time_s)

    def test_materialisation_preserves_clear_point_set(self):
        points = ((0.0, 0.0), (27.0, 0.0), (0.0, 27.0))
        spec = SourceServiceSpec(
            channel=3,
            mode="direct_clear",
            entry_point=None,
            entry_action_kind="clear",
            entry_action_channel=3,
            route_points=points,
            source_version=(3,),
        )
        first = materialize_service_block(spec, (-50.0, 0.0), 1)
        second = materialize_service_block(spec, (50.0, 0.0), 1)
        self.assertEqual(set(first.route_points), set(points))
        self.assertEqual(set(second.route_points), set(points))

    def test_bounded_cache_preserves_route_and_clear_cost_values(self):
        specs = {
            channel: self._certified_spec(channel, point)
            for channel, point in {
                1: (100.0, 0.0), 2: (0.0, 100.0), 3: (200.0, 0.0),
            }.items()
        }
        uncached = plan_service_route(
            specs, (0.0, 0.0), 1, cpu_time_limit_s=1.0
        )
        cache = Q3ComputationCache(capacity=128)
        cached = plan_service_route(
            specs, (0.0, 0.0), 1, cpu_time_limit_s=1.0,
            cache=cache,
        )
        repeated = plan_service_route(
            specs, (0.0, 0.0), 1, cpu_time_limit_s=1.0,
            cache=cache,
        )
        self.assertEqual(uncached.estimate, cached.estimate)
        self.assertEqual(cached.estimate, repeated.estimate)

        region = self._small_region(20.0)
        uncached_clear = clear_plan_cost(region, (3.0, 4.0))
        cached_clear = clear_plan_cost(
            region, (3.0, 4.0), cache=cache
        )
        repeated_clear = clear_plan_cost(
            region, (3.0, 4.0), cache=cache
        )
        self.assertEqual(uncached_clear, cached_clear)
        self.assertEqual(cached_clear, repeated_clear)
        self.assertGreater(cache.snapshot()["hits"], 0)

    def test_q2_cache_key_invalidates_on_state_changes(self):
        policy = Q3Policy(
            computation_cache_mode="bounded", cache_capacity=32
        )
        track = SourceTrack(3, region=self._small_region())
        state = Q3State(position=(0.0, 0.0), current_channel=1)
        counter = {"value": 0}

        def fake_plan(*args, **kwargs):
            counter["value"] += 1
            return {"marker": counter["value"]}

        with patch("q3.policy.plan_measurement", side_effect=fake_plan):
            first = policy._refinement_plan(state, track)
            second = policy._refinement_plan(state, track)
            state.position = (1.0, 0.0)
            moved = policy._refinement_plan(state, track)
            state.current_channel = 2
            switched = policy._refinement_plan(state, track)
            track.observations.append(BearingObservation(
                (1.0, 0.0), 3, "direction", 0.0
            ))
            observed = policy._refinement_plan(state, track)
        self.assertEqual(first, second)
        self.assertEqual(
            [first["marker"], moved["marker"], switched["marker"],
             observed["marker"]],
            [1, 2, 3, 4],
        )
        q2_stats = policy.computation_cache.snapshot()[
            "namespaces"
        ]["q2_plan"]
        self.assertEqual(q2_stats["hits"], 1)
        self.assertEqual(q2_stats["misses"], 4)

    def test_cache_capacity_eviction_does_not_change_values(self):
        cache = Q3ComputationCache(capacity=2)
        self.assertEqual(cache.get_or_compute("test", "a", lambda: 1), 1)
        self.assertEqual(cache.get_or_compute("test", "b", lambda: 2), 2)
        self.assertEqual(cache.get_or_compute("test", "c", lambda: 3), 3)
        self.assertEqual(cache.get_or_compute("test", "a", lambda: 1), 1)
        snapshot = cache.snapshot()
        self.assertEqual(snapshot["entries"], 2)
        self.assertGreaterEqual(snapshot["evictions"], 2)

    def test_beam_search_is_deterministic_and_not_worse_than_width_one(self):
        specs = {
            channel: self._certified_spec(channel, point)
            for channel, point in {
                1: (100.0, 70.0), 2: (10.0, 160.0),
                3: (170.0, 10.0), 4: (80.0, 170.0),
                5: (180.0, 120.0),
            }.items()
        }
        narrow = plan_beam_cached_route(
            specs, (0.0, 0.0), 1, cpu_time_limit_s=2.0,
            beam_width=1, max_expansions=256,
            cache=Q3ComputationCache(capacity=1024),
        )
        wide = plan_beam_cached_route(
            specs, (0.0, 0.0), 1, cpu_time_limit_s=2.0,
            beam_width=4, max_expansions=256,
            cache=Q3ComputationCache(capacity=1024),
        )
        repeated = plan_beam_cached_route(
            specs, (0.0, 0.0), 1, cpu_time_limit_s=2.0,
            beam_width=4, max_expansions=256,
            cache=Q3ComputationCache(capacity=1024),
        )
        self.assertEqual(narrow.status, "ok")
        self.assertEqual(wide.status, "ok")
        self.assertLessEqual(
            wide.estimate.total_virtual_time_s,
            narrow.estimate.total_virtual_time_s + 1e-9,
        )
        self.assertEqual(wide.estimate, repeated.estimate)

    def test_beam_expansion_limit_returns_complete_insertion_fallback(self):
        specs = {
            channel: self._certified_spec(channel, (channel * 20.0, 0.0))
            for channel in range(1, 5)
        }
        result = plan_beam_cached_route(
            specs, (0.0, 0.0), 1, cpu_time_limit_s=2.0,
            beam_width=2, max_expansions=1,
            cache=Q3ComputationCache(capacity=1024),
        )
        self.assertEqual(result.status, "partial")
        self.assertIsNotNone(result.estimate)
        self.assertEqual(set(result.estimate.order), set(specs))
        self.assertEqual(result.fallback_solver, "insertion_2opt")

    def test_rolling_clear_cost_uses_execution_grid_and_route_accounting(self):
        region = self._small_region(5.0)
        with patch("q3.rolling_time.posterior_clear_points",
                   return_value=[(0.0, 0.0), (10.0, 0.0)]):
            result = clear_plan_cost(region, (0.0, 0.0))
            continued = clear_plan_cost(
                region, (0.0, 0.0), continuation_points=[(20.0, 0.0)]
            )
        self.assertEqual(result["point_count"], 2)
        self.assertAlmostEqual(result["cost_s"], 10.0)
        self.assertAlmostEqual(continued["base_clear_cost_s"], 10.0)
        self.assertAlmostEqual(continued["continuation_cost_s"], 2.0)
        self.assertAlmostEqual(continued["cost_s"], 12.0)

    def test_rolling_candidate_time_counts_move_switch_and_measure_once(self):
        track = SourceTrack(
            3,
            observations=[BearingObservation(
                (-100.0, 0.0), 3, "direction", 0.0
            )],
            region=self._small_region(),
        )
        with patch("q3.rolling_time._posterior_branch", return_value={
                "clear_cost_s": 30.0,
                "clear_point_count": 4,
                "branch": "direction",
        }) as branch:
            result = evaluate_candidate(
                track, (30.0, 40.0),
                current_position=(0.0, 0.0), current_channel=1,
                config=Q3Policy().q2_config, scenario_limit=1,
            )
        self.assertAlmostEqual(result["measure_action_time_s"], 16.0)
        self.assertAlmostEqual(result["post_clear_p90_s"], 30.0)
        self.assertEqual(result["scenario_count"], 3)
        self.assertEqual(branch.call_count, 3)

    def test_rolling_selects_lower_total_route_not_smaller_q2_radius(self):
        track = SourceTrack(
            3,
            observations=[BearingObservation(
                (-100.0, 0.0), 3, "direction", 0.0
            )],
            region=self._small_region(),
        )
        plan = {
            "selected": {
                "point": (0.0, 0.0), "worst_case_radius_m": 10.0,
            },
            "baseline": {"selected": {
                "point": (100.0, 0.0), "worst_case_radius_m": 30.0,
            }},
            "continuous_fim": {"status": "disabled"},
            "pareto_front": [], "candidates": [],
            "candidate_regions": {},
        }

        def candidate_result(_track, point, **_kwargs):
            if tuple(point) == (0.0, 0.0):
                return self._rolling_candidate_result(point, 5.0, 70.0)
            return self._rolling_candidate_result(point, 25.0, 20.0)

        with (patch("q3.rolling_time.clear_plan_cost",
                    return_value={"cost_s": 100.0, "point_count": 8}),
              patch("q3.rolling_time.evaluate_candidate",
                    side_effect=candidate_result)):
            decision = evaluate_total_time_decision(
                track, plan,
                current_position=(0.0, 0.0), current_channel=3,
                config=Q3Policy().q2_config,
                savings_margin_s=10.0,
            )
        self.assertEqual(decision["decision"], "measure")
        self.assertEqual(decision["selected_point"], (100.0, 0.0))
        self.assertAlmostEqual(decision["estimated_total_cost_s"], 45.0)

    def test_rolling_timeout_falls_back_to_finite_clear(self):
        track = SourceTrack(
            3,
            observations=[BearingObservation(
                (-100.0, 0.0), 3, "direction", 0.0
            )],
            region=self._small_region(),
        )
        plan = {
            "selected": {"point": (0.0, 0.0)},
            "baseline": {}, "continuous_fim": {"status": "disabled"},
            "pareto_front": [], "candidates": [], "candidate_regions": {},
        }
        with (patch("q3.rolling_time.clear_plan_cost",
                    return_value={"cost_s": 100.0, "point_count": 8}),
              patch("q3.rolling_time.evaluate_candidate", return_value=None)):
            decision = evaluate_total_time_decision(
                track, plan,
                current_position=(0.0, 0.0), current_channel=3,
                config=Q3Policy().q2_config,
            )
        self.assertEqual(decision["decision"], "clear")
        self.assertEqual(decision["solver_status"], "fallback")
        self.assertTrue(decision["timed_out"])

    def test_rolling_switch_is_independent_and_q4_keeps_it_off(self):
        observation = BearingObservation(
            (-100.0, 0.0), 3, "direction", 0.0
        )
        track = SourceTrack(3, [observation], self._small_region())
        state = Q3State(
            entered=True, phase="resolve", sources={3: track},
            current_channel=3,
        )
        plan = {
            "selected": {"point": (20.0, 0.0),
                         "worst_case_radius_m": 20.0,
                         "action_time_s": 9.0},
            "continuous_fim": {"status": "disabled"},
        }
        old = Q3Policy(
            joint_batch_mode="off", rolling_time_mode="off",
            failed_clear_remeasure_mode="off",
        )
        with (patch.object(old, "_refinement_plan", return_value=plan),
              patch("q3.policy.posterior_clear_points",
                    return_value=[(0.0, 0.0), (20.0, 0.0)]),
              patch("q3.policy.measurement_is_worthwhile", return_value=True),
              patch("q3.policy.evaluate_total_time_decision") as evaluator):
            action = old.next_action(state)
        self.assertEqual(action.kind, "measure")
        evaluator.assert_not_called()

        rolling_track = SourceTrack(3, [observation], self._small_region())
        rolling_state = Q3State(
            entered=True, phase="resolve", sources={3: rolling_track},
            current_channel=3,
        )
        rolling = Q3Policy(
            joint_batch_mode="off", rolling_time_mode="scenario",
            failed_clear_remeasure_mode="off",
        )
        decision = {
            "decision": "measure", "selected_point": (40.0, 0.0),
            "measure_action_time_s": 13.0, "estimated_saving_s": 30.0,
            "solver_status": "ok", "timed_out": False,
        }
        with (patch.object(rolling, "_refinement_plan", return_value=plan),
              patch("q3.policy.posterior_clear_points",
                    return_value=[(0.0, 0.0), (20.0, 0.0)]),
              patch("q3.policy.evaluate_total_time_decision",
                    return_value=decision) as evaluator):
            action = rolling.next_action(rolling_state)
        self.assertEqual(action.position, (40.0, 0.0))
        self.assertEqual(rolling_track.rolling_decision_count, 1)
        evaluator.assert_called_once()
        self.assertEqual(Q4Policy().rolling_time_mode, "off")

    def test_rolling_risk_summary_is_deterministic(self):
        first = risk_summary([30.0, 10.0, 40.0, 20.0])
        second = risk_summary([20.0, 40.0, 10.0, 30.0])
        self.assertEqual(first, second)
        self.assertEqual(first["p90_s"], 40.0)

    def test_failed_clear_remeasure_evaluator_applies_profit_gate(self):
        track = SourceTrack(
            3,
            observations=[BearingObservation(
                (-100.0, 0.0), 3, "direction", 0.0
            )],
            region=self._small_region(),
        )
        evaluation = {
            "guaranteed_reception": True,
            "worst_case_radius_m": 20.0,
            "action_time_s": 5.0,
        }
        with patch(
                "q3.fallback_remeasure.fixed_point_evaluation",
                return_value=evaluation):
            decision = evaluate_failed_clear_remeasure(
                track, (0.0, 0.0),
                [(20.0, 0.0), (40.0, 0.0), (60.0, 0.0)],
                current_channel=3,
                config=Q3Policy().q2_config,
                min_baseline_m=40.0,
                savings_margin_s=2.0,
            )
        self.assertTrue(decision["worthwhile"])
        self.assertEqual(decision["reason"], "predicted_saving")

    def test_failed_clear_triggers_exactly_one_decision_and_same_point_measure(self):
        policy = Q3Policy(
            joint_batch_mode="off",
            failed_clear_remeasure_mode="gated",
        )
        track = SourceTrack(
            3,
            observations=[BearingObservation(
                (-100.0, 0.0), 3, "direction", 0.0
            )],
            region=self._small_region(),
            refinement_stopped=True,
            fallback_points=[(0.0, 0.0), (20.0, 0.0),
                             (40.0, 0.0), (60.0, 0.0)],
            fallback_index=1,
            failed_clear_points=[(0.0, 0.0)],
            fallback_remeasure_pending=True,
        )
        state = Q3State(
            entered=True, phase="resolve", position=(0.0, 0.0),
            current_channel=3, sources={3: track},
        )
        decision = {"worthwhile": True, "reason": "predicted_saving"}
        with patch("q3.policy.evaluate_failed_clear_remeasure",
                   return_value=decision) as evaluator:
            action = policy.next_action(state)
        self.assertEqual(action.kind, "measure")
        self.assertEqual(action.position, (0.0, 0.0))
        self.assertEqual(action.channel, 3)
        self.assertEqual(state.pending_mode, "fallback_remeasure")
        self.assertEqual(track.fallback_remeasure_checks, 1)
        evaluator.assert_called_once()

        policy.apply_response(state, action, {
            "accepted": True,
            "virtual_time_s": 5.0,
            "measure_result": "no_signal",
        })
        next_action = policy.next_action(state)
        self.assertEqual(next_action.kind, "clear")
        self.assertEqual(next_action.position, (20.0, 0.0))
        self.assertEqual(track.fallback_remeasure_checks, 1)

    def test_valid_failed_clear_remeasure_rebuilds_remaining_grid(self):
        policy = Q3Policy(joint_batch_mode="off")
        track = SourceTrack(
            3,
            observations=[BearingObservation(
                (-100.0, 0.0), 3, "direction", 0.0
            )],
            region=self._small_region(),
            refinement_stopped=True,
            fallback_points=[(0.0, 0.0), (20.0, 0.0)],
            fallback_index=1,
            failed_clear_points=[(0.0, 0.0)],
        )
        state = Q3State(
            entered=True, phase="resolve", position=(0.0, 0.0),
            current_channel=3, sources={3: track},
        )
        action = policy._action(
            state, "measure", (0.0, 0.0), 3, "fallback_remeasure"
        )
        updated = self._small_region(40.0)
        with (patch("q3.policy.build_region_from_observations",
                    return_value=updated),
              patch("q3.policy.posterior_clear_points",
                    return_value=[(0.0, 0.0), (20.0, 0.0),
                                  (40.0, 0.0)])):
            policy.apply_response(state, action, {
                "accepted": True,
                "virtual_time_s": 5.0,
                "measure_result": "direction",
                "svd_deg": 10.0,
            })
        self.assertEqual(track.fallback_remeasure_count, 1)
        self.assertEqual(track.fallback_remeasure_points, [(0.0, 0.0)])
        self.assertEqual(track.fallback_index, 0)
        self.assertNotIn((0.0, 0.0), track.fallback_points)
        self.assertEqual(set(track.fallback_points), {(20.0, 0.0),
                                                       (40.0, 0.0)})

    def test_failed_fallback_clear_sets_one_pending_check_and_q4_disables_it(self):
        policy = Q3Policy(joint_batch_mode="off")
        track = SourceTrack(
            3, region=self._small_region(), refinement_stopped=True,
            fallback_points=[(0.0, 0.0), (20.0, 0.0)],
        )
        state = Q3State(
            entered=True, phase="resolve", sources={3: track},
        )
        action = policy._action(
            state, "clear", (0.0, 0.0), 3, "fallback_clear"
        )
        policy.apply_response(state, action, {
            "accepted": True,
            "virtual_time_s": 3.0,
            "clear_result": "no_target_in_range",
        })
        self.assertTrue(track.fallback_remeasure_pending)
        self.assertEqual(track.failed_clear_disks, [((0.0, 0.0), 20.0)])
        self.assertEqual(Q4Policy().failed_clear_remeasure_mode, "off")

    def test_refinement_consumes_q2_hybrid_recommendation(self):
        policy = Q3Policy()
        state = Q3State(position=(10.0, 20.0), current_channel=2)
        track = SourceTrack(
            3,
            observations=[BearingObservation(
                (0.0, 0.0), 3, "direction", 45.0
            )],
            region={"status": "bounded"},
        )
        fake_plan = {
            "selected": {"point": (1.0, 2.0)},
            "continuous_fim": {
                "status": "ok",
                "selected": {"point": (80.0, 90.0)},
            },
        }
        with patch("q3.policy.plan_measurement",
                   return_value=fake_plan) as planner:
            self.assertEqual(policy._refinement_point(state, track),
                             (80.0, 90.0))
        self.assertTrue(policy.q2_config.continuous_fim_enabled)
        self.assertEqual(policy.q2_config.fim_cpu_time_limit_s, 10.0)
        self.assertEqual(policy.q2_config.near_optimal_region_mode, "off")
        self.assertEqual(policy.max_opportunistic_per_source, 3)
        self.assertEqual(policy.rolling_cpu_time_limit_s, 1.0)
        planner.assert_called_once()

    def test_posterior_grid_uses_27_metres_with_safe_cover_radius(self):
        self.assertEqual(DEFAULT_CLEAR_GRID_SPACING_M, 27.0)
        self.assertLess(
            DEFAULT_CLEAR_GRID_SPACING_M / math.sqrt(2.0) + 1e-7,
            CLEAR_RADIUS_M,
        )
        planes = [
            (1.0, 0.0, 75.0), (-1.0, 0.0, 75.0),
            (0.0, 1.0, 55.0), (0.0, -1.0, 55.0),
        ]
        region = intersect_halfplanes(planes)
        region["planes"] = planes
        points = posterior_clear_points(region)
        rng = random.Random(317)
        worst = 0.0
        for _ in range(5000):
            target = (rng.uniform(-75.0, 75.0),
                      rng.uniform(-55.0, 55.0))
            worst = max(worst, min(math.dist(target, point)
                                   for point in points))
        self.assertLess(worst, 20.0)

    def test_measurement_decision_requires_predicted_time_saving(self):
        self.assertTrue(measurement_is_worthwhile(
            100.0, 40.0, 30.0, margin_s=10.0,
            current_clear_cost_s=200.0,
        ))
        self.assertFalse(measurement_is_worthwhile(
            100.0, 95.0, 30.0, margin_s=10.0,
            current_clear_cost_s=200.0,
        ))

    def test_joint_plan_batches_profitable_channels_at_one_point(self):
        policy = Q3Policy(
            joint_batch_mode="guaranteed", rolling_time_mode="off"
        )
        observation = BearingObservation((0.0, 0.0), 3, "direction", 0.0)
        region = {
            "status": "bounded",
            "minimum_enclosing_circle": {"center": (100.0, 0.0),
                                           "radius": 100.0},
        }
        state = Q3State(
            phase="resolve",
            sources={
                3: SourceTrack(3, [observation], dict(region)),
                7: SourceTrack(7, [BearingObservation(
                    (0.0, 10.0), 7, "direction", 0.0
                )], dict(region)),
            },
        )
        selected = {
            "point": (200.0, 100.0),
            "worst_case_radius_m": 20.0,
            "action_time_s": 30.0,
        }
        fake_plan = {
            "selected": selected,
            "continuous_fim": {"status": "ok", "selected": selected},
        }
        fixed = {
            "guaranteed_reception": True,
            "worst_case_radius_m": 20.0,
            "action_time_s": 6.0,
        }
        with (patch.object(policy, "_refinement_plan",
                           return_value=fake_plan),
              patch("q3.policy.direct_clear_cost",
                    return_value=(200.0, [])),
              patch("q3.policy.fixed_point_evaluation",
                    return_value=fixed)):
            plan, rejected = policy._joint_plan(state, [3, 7])
        self.assertEqual(plan["point"], (200.0, 100.0))
        self.assertEqual(set(plan["channels"]), {3, 7})
        self.assertEqual(rejected, set())
        policy._start_joint_batch(state, plan)
        first = policy._next_joint_batch_action(state)
        state.pending = None
        state.batch_index += 1
        second = policy._next_joint_batch_action(state)
        self.assertEqual(first.position, second.position)
        self.assertNotEqual(first.channel, second.channel)

    def test_route_selection_keeps_single_source_point_and_does_not_stop_other(self):
        policy = Q3Policy(multi_source_route_mode="insertion_2opt")
        region = self._small_region()
        state = Q3State(
            entered=True,
            phase="resolve",
            sources={
                3: SourceTrack(3, [BearingObservation(
                    (-100.0, 0.0), 3, "direction", 0.0
                )], region),
                7: SourceTrack(7, [BearingObservation(
                    (0.0, -100.0), 7, "direction", 90.0
                )], region),
            },
        )
        option = {
            "point": (40.0, 50.0),
            "channels": [7],
            "target_channel": 7,
            "estimated_saving_s": 50.0,
            "target_action_time_s": 20.0,
            "single_source_decision": {"decision": "measure"},
        }
        estimate = RouteEstimate(
            order=(7, 3), blocks=(), total_virtual_time_s=100.0,
            total_movement_distance_m=200.0, long_jump_count=0,
            long_jump_distance_m=0.0, end_position=(0.0, 0.0),
            end_channel=7,
        )
        route_plan = RoutePlan(
            status="ok", reason="complete", estimate=estimate,
            insertion_order=(3, 7), two_opt_iterations=1,
            cpu_wall_time_s=0.01,
        )
        with (patch.object(policy, "_build_joint_options",
                           return_value=([option], {3})),
              patch("q3.policy.plan_service_route",
                    return_value=route_plan)):
            action = policy.next_action(state)
        self.assertEqual(action.kind, "measure")
        self.assertEqual(action.channel, 7)
        self.assertEqual(action.position, option["point"])
        self.assertFalse(state.sources[3].refinement_stopped)

    def test_route_finishes_existing_joint_batch_before_replanning(self):
        policy = Q3Policy(multi_source_route_mode="insertion_2opt")
        region = self._small_region()
        state = Q3State(
            entered=True, phase="resolve",
            sources={3: SourceTrack(3, [BearingObservation(
                (-100.0, 0.0), 3, "direction", 0.0
            )], region)},
            batch_point=(20.0, 30.0), batch_channels=[3],
            batch_target_channel=3,
        )
        with patch("q3.policy.plan_service_route",
                   side_effect=AssertionError("batch must finish first")):
            action = policy.next_action(state)
        self.assertEqual(action.kind, "measure")
        self.assertEqual(action.position, (20.0, 30.0))
        self.assertEqual(state.pending_mode, "joint_target")

    def test_route_fallback_uses_existing_joint_selector(self):
        policy = Q3Policy(multi_source_route_mode="insertion_2opt")
        region = self._small_region()
        state = Q3State(
            entered=True, phase="resolve",
            sources={3: SourceTrack(3, [BearingObservation(
                (-100.0, 0.0), 3, "direction", 0.0
            )], region)},
        )
        option = {
            "point": (20.0, 30.0),
            "channels": [3],
            "target_channel": 3,
            "estimated_saving_s": 50.0,
            "target_action_time_s": 15.0,
            "single_source_decision": {"decision": "measure"},
        }
        fallback = RoutePlan(
            status="fallback", reason="test", estimate=None,
            insertion_order=(), two_opt_iterations=0,
            cpu_wall_time_s=0.01,
        )
        with (patch.object(policy, "_build_joint_options",
                           return_value=([option], set())),
              patch("q3.policy.plan_service_route", return_value=fallback)):
            action = policy.next_action(state)
        self.assertEqual(action.kind, "measure")
        self.assertEqual(action.channel, 3)
        self.assertEqual(action.position, option["point"])
        self.assertEqual(policy.route_planning_history[-1]["status"],
                         "fallback")

    def test_route_mode_keeps_near_clear_forced_priority(self):
        policy = Q3Policy(multi_source_route_mode="insertion_2opt")
        state = Q3State(
            entered=True, phase="resolve",
            forced_clear=((12.0, 13.0), 3),
        )
        with patch("q3.policy.plan_service_route",
                   side_effect=AssertionError("near clear must be first")):
            action = policy.next_action(state)
        self.assertEqual(action.kind, "clear")
        self.assertEqual(action.position, (12.0, 13.0))
        self.assertEqual(state.pending_mode, "near_clear")

    def test_q4_explicitly_keeps_multi_source_route_off(self):
        self.assertEqual(Q4Policy().multi_source_route_mode, "off")

    def test_guaranteed_batch_rejects_uncovered_extra_channel(self):
        policy = Q3Policy(joint_batch_mode="guaranteed")
        evaluation = {
            "guaranteed_reception": False,
            "worst_case_radius_m": 10.0,
            "action_time_s": 6.0,
        }
        self.assertFalse(policy._include_batch_evaluation(evaluation, 100.0))
        all_active = Q3Policy(joint_batch_mode="all_active")
        self.assertTrue(all_active._include_batch_evaluation(evaluation,
                                                             -100.0))

    def test_scan_batch_uses_guaranteed_stop_without_savings_gate(self):
        policy = Q3Policy(joint_batch_mode="guaranteed")
        observation = BearingObservation(
            (0.0, 0.0), 3, "direction", 0.0
        )
        region = {
            "status": "bounded",
            "minimum_enclosing_circle": {
                "center": (100.0, 0.0), "radius": 100.0,
            },
        }
        state = Q3State(
            current_channel=7,
            sources={3: SourceTrack(3, [observation], region)},
        )
        guaranteed = {
            "guaranteed_reception": True,
            "worst_case_radius_m": 99.0,
            "action_time_s": 1000.0,
        }
        with (patch("q3.policy.direct_clear_cost",
                    side_effect=AssertionError("scan must not price clear")),
              patch("q3.policy.fixed_point_evaluation",
                    return_value=guaranteed),
              patch("q3.policy.marginal_saving",
                    side_effect=AssertionError("scan must not gate savings"))):
            channels = policy._prepare_scan_batch(state, (10.0, 0.0))
        self.assertEqual(channels, [3])

        uncovered = dict(guaranteed, guaranteed_reception=False)
        with (patch("q3.policy.direct_clear_cost",
                    side_effect=AssertionError("scan must not price clear")),
              patch("q3.policy.fixed_point_evaluation",
                    return_value=uncovered),
              patch("q3.policy.marginal_saving",
                    side_effect=AssertionError("scan must not gate savings"))):
            channels = policy._prepare_scan_batch(state, (10.0, 0.0))
        self.assertEqual(channels, [])

    def test_ring7_covers_random_target_disk_at_radius_1000(self):
        rng = random.Random(20260911)
        centers = ring7()
        worst = 0.0
        for _ in range(5000):
            radius = 1800*math.sqrt(rng.random())
            angle = 2*math.pi*rng.random()
            point = (radius*math.cos(angle), radius*math.sin(angle))
            worst = max(worst, nearest_coverage_distance(point, centers))
        self.assertLessEqual(worst, 1000.0)

    def test_strip_clear_grid_covers_full_bearing_rectangle(self):
        points = list(strip_clear_points((0.0, 0.0), 0.0))
        worst = 0.0
        for x in range(0, 1501, 10):
            for y in (-26.32, -13.16, 0.0, 13.16, 26.32):
                worst = max(worst, min(math.dist((x, y), p) for p in points))
        self.assertLess(worst, 20.0)

    def test_official_199_second_accounting_example(self):
        client = FakeSimulator([])
        actions = [
            Action("enter", "e"),
            Action("measure", "m1", (300.0, 400.0), 1),
            Action("measure", "m2", (300.0, 400.0), 2),
            Action("clear", "c1", (300.0, 0.0), 3),
            Action("measure", "m3", (300.0, 0.0), 2),
        ]
        for action in actions:
            response = client.execute(action)
        self.assertAlmostEqual(response["virtual_time_s"], 199.0)

    def test_request_id_is_idempotent_in_fake_client(self):
        client = FakeSimulator([])
        client.execute(Action("enter", "enter"))
        action = Action("measure", "same", (300.0, 400.0), 1)
        first = client.execute(action)
        second = client.execute(action)
        self.assertEqual(first, second)
        self.assertEqual(client.virtual_time, 105.0)

    def test_official_payload_does_not_leak_internal_fields(self):
        action = Action("measure", "m-1", (1.0, 2.0), 4)
        payload = build_request_payload(action, "team")
        self.assertEqual(set(payload), {"arena_id", "robot_id", "request_id",
                                        "position", "channel"})
        self.assertNotIn("kind", payload)

    def test_q3_policy_finitely_clears_and_certifies_channels_offline(self):
        class CountingQ3Policy(Q3Policy):
            def __init__(self):
                super().__init__(max_refinements=2)
                self.refinement_plan_count = 0

            def _refinement_plan(self, state, track):
                self.refinement_plan_count += 1
                return super()._refinement_plan(state, track)

        client = FakeSimulator([FakeSource(3, (1200.0, 100.0), 1000.0)])
        policy = CountingQ3Policy()
        summary = run_policy(policy, client, max_actions=1000)
        self.assertEqual(summary.cleared_channels, [3])
        self.assertEqual(summary.absent_channels,
                         [c for c in range(1, 21) if c != 3])
        self.assertEqual(summary.exit_reason, "user_exit")
        self.assertLess(len(summary.actions), 1000)
        self.assertGreaterEqual(policy.refinement_plan_count, 1)
        self.assertLessEqual(policy.refinement_plan_count, 2)


if __name__ == "__main__":
    unittest.main()
