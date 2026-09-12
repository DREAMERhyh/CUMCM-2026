"""Q4 mixed-source policy built on the Q3 execution state machine."""

from dataclasses import dataclass, field
import math

from common.time_model import measure_cost
from q3.policy import Q3Policy, Q3State
from q3.route import SourceServiceSpec, plan_service_route

from .belief import Q4Measurement, build_joint_belief
from .directional import (adaptive_four_sided_points,
                          certified_probe_points, grid121, triangular37)
from .rolling import evaluate_directional_probe_decision


@dataclass
class ProbeBundle:
    points: tuple[tuple[float, float], ...]
    remaining: list[tuple[float, float]]
    initial_radius_m: float
    kind: str = "unknown"
    pending_point: tuple[float, float] | None = None
    outcomes: list[str] = field(default_factory=list)


@dataclass
class Q4State(Q3State):
    measure_history: dict[int, list[Q4Measurement]] = field(
        default_factory=dict
    )
    joint_beliefs: dict[int, object] = field(default_factory=dict)
    probe_bundles: dict[int, ProbeBundle] = field(default_factory=dict)
    probe_bundle_counts: dict[int, int] = field(default_factory=dict)
    probe_diagnostics: list[dict] = field(default_factory=list)
    rolling_diagnostics: list[dict] = field(default_factory=list)
    long_clear_rescue_counts: dict[int, int] = field(default_factory=dict)
    long_clear_diagnostics: list[dict] = field(default_factory=list)
    rescue_probe_channels: set[int] = field(default_factory=set)
    route_active_channel: int | None = None


class Q4Policy(Q3Policy):
    """Certified mixed omni/directional search with finite belief ranking.

    ``max_refinements`` counts started certified probe bundles, not individual
    probe points.  A bundle stops after ``direction``/``near``; after
    ``no_signal`` the Q4 rolling gate either retains the remaining certified
    points or switches to the independently certified posterior clear cover.
    """

    def __init__(self, *, max_refinements=2, error_deg=1.005,
                 fim_cpu_time_limit_s=6.0, scan_mode="triangular37",
                 q2_version="new",
                 coverage_points=None, belief_position_limit=12,
                 belief_direction_step_deg=10,
                 failed_clear_remeasure_mode="gated",
                 max_failed_clear_remeasures_per_source=3,
                 min_remaining_clear_points_for_remeasure=3,
                 min_remeasure_baseline_m=40.0,
                 failed_clear_measure_margin_s=2.0,
                 directional_rolling_mode="scenario",
                 directional_rolling_savings_margin_s=10.0,
                 directional_rolling_risk_metric="cvar",
                 directional_rolling_cvar_alpha=0.9,
                 directional_rolling_scenario_limit=48,
                 directional_rolling_candidate_limit=8,
                 directional_rolling_cpu_time_limit_s=3.0,
                 directional_probe_spacing_m=900.0,
                 long_clear_tail_mode="adaptive",
                 long_clear_rescue_failure_threshold=8,
                 max_long_clear_rescues_per_source=1,
                 multi_source_route_mode="off",
                 route_cpu_time_limit_s=0.25,
                 route_max_2opt_iterations=20):
        if scan_mode not in ("triangular37", "grid121", "custom"):
            raise ValueError("Q4扫描模式必须为triangular37、grid121或custom。")
        if coverage_points is not None:
            selected_coverage = list(coverage_points)
            scan_mode = "custom"
        elif scan_mode == "triangular37":
            selected_coverage = triangular37()
        elif scan_mode == "grid121":
            selected_coverage = grid121()
        else:
            raise ValueError("custom扫描模式必须显式提供coverage_points。")
        if belief_position_limit < 1:
            raise ValueError("Q4联合后验位置场景上限至少为1。")
        if (belief_direction_step_deg < 1
                or 360 % belief_direction_step_deg != 0):
            raise ValueError("Q4方向步长必须是360的正整数因子。")
        if directional_rolling_mode not in ("off", "scenario"):
            raise ValueError("Q4方向滚动模式必须为off或scenario。")
        if directional_rolling_risk_metric not in (
                "mean", "p90", "cvar", "worst"):
            raise ValueError("Q4方向滚动风险指标非法。")
        if not 0.0 < directional_rolling_cvar_alpha < 1.0:
            raise ValueError("Q4方向滚动CVaR分位必须位于(0,1)。")
        if (directional_rolling_scenario_limit < 1
                or directional_rolling_candidate_limit < 1
                or directional_rolling_cpu_time_limit_s <= 0.0):
            raise ValueError("Q4方向滚动场景、候选和CPU上限必须为正。")
        if (directional_rolling_savings_margin_s < 0.0
                or directional_probe_spacing_m <= 0.0
                or directional_probe_spacing_m
                > 1000.0):
            raise ValueError("Q4滚动余量或定向探测网间距非法。")
        if long_clear_tail_mode not in ("off", "adaptive"):
            raise ValueError("Q4长清除尾模式必须为off或adaptive。")
        if (long_clear_rescue_failure_threshold < 1
                or max_long_clear_rescues_per_source < 0):
            raise ValueError("Q4长清除尾门控参数非法。")
        if multi_source_route_mode not in ("off", "insertion_2opt"):
            raise ValueError("Q4多源路线只支持off或insertion_2opt。")

        super().__init__(
            max_refinements=max_refinements,
            error_deg=error_deg,
            coverage_points=selected_coverage,
            fim_cpu_time_limit_s=fim_cpu_time_limit_s,
            q2_version=q2_version,
            adaptive_refinement=False,
            posterior_grid=True,
            joint_batch_mode="off",
            failed_clear_remeasure_mode=failed_clear_remeasure_mode,
            max_failed_clear_remeasures_per_source=(
                max_failed_clear_remeasures_per_source
            ),
            min_remaining_clear_points_for_remeasure=(
                min_remaining_clear_points_for_remeasure
            ),
            min_remeasure_baseline_m=min_remeasure_baseline_m,
            failed_clear_measure_margin_s=failed_clear_measure_margin_s,
            rolling_time_mode="off",
            multi_source_route_mode=multi_source_route_mode,
            route_cpu_time_limit_s=route_cpu_time_limit_s,
            route_max_2opt_iterations=route_max_2opt_iterations,
        )
        self.scan_mode = scan_mode
        self.belief_position_limit = belief_position_limit
        self.belief_direction_step_deg = belief_direction_step_deg
        self.directional_rolling_mode = directional_rolling_mode
        self.directional_rolling_savings_margin_s = (
            directional_rolling_savings_margin_s
        )
        self.directional_rolling_risk_metric = (
            directional_rolling_risk_metric
        )
        self.directional_rolling_cvar_alpha = directional_rolling_cvar_alpha
        self.directional_rolling_scenario_limit = (
            directional_rolling_scenario_limit
        )
        self.directional_rolling_candidate_limit = (
            directional_rolling_candidate_limit
        )
        self.directional_rolling_cpu_time_limit_s = (
            directional_rolling_cpu_time_limit_s
        )
        self.directional_probe_spacing_m = directional_probe_spacing_m
        self.long_clear_tail_mode = long_clear_tail_mode
        self.long_clear_rescue_failure_threshold = (
            long_clear_rescue_failure_threshold
        )
        self.max_long_clear_rescues_per_source = (
            max_long_clear_rescues_per_source
        )

    def initial_state(self):
        return Q4State()

    def _can_refine(self, track, state=None):
        if track.refinement_stopped or track.certificate_failed:
            return False
        if state is None:
            return track.refinements < self.max_refinements
        bundle = state.probe_bundles.get(track.channel)
        if bundle is not None and bundle.remaining:
            return True
        return (state.probe_bundle_counts.get(track.channel, 0)
                < self.max_refinements)

    def _refresh_belief(self, state, track):
        history = state.measure_history.get(track.channel, ())
        belief = build_joint_belief(
            track.region,
            history,
            error_deg=self.error_deg,
            arena_radius=self.q2_config.arena_radius,
            position_limit=self.belief_position_limit,
            direction_step_deg=self.belief_direction_step_deg,
            excluded_disks=track.failed_clear_disks,
        )
        state.joint_beliefs[track.channel] = belief
        return belief

    @staticmethod
    def _measurement_record(action, response):
        result = response["measure_result"]
        return Q4Measurement(
            tuple(action.position), result,
            response.get("svd_deg") if result == "direction" else None,
        )

    def _probe_points(self, state, track):
        if self.directional_rolling_mode == "off":
            circle = track.region["minimum_enclosing_circle"]
            points = adaptive_four_sided_points(
                tuple(circle["center"]), circle["radius"],
                min_receive_radius=self.q2_config.min_receive_radius,
            )
            if not points:
                raise RuntimeError("当前后验不存在紧凑四侧探测证书。")
            return points, "four_sided"
        return certified_probe_points(
            track.region,
            spacing=self.directional_probe_spacing_m,
            min_receive_radius=self.q2_config.min_receive_radius,
            phase_index=state.probe_bundle_counts.get(track.channel, 0),
        )

    def _start_probe_bundle(self, state, track, points=None, kind=None):
        circle = track.region["minimum_enclosing_circle"]
        if points is None:
            points, kind = self._probe_points(state, track)
        points = tuple(tuple(point) for point in points)
        if not points:
            return None
        bundle = ProbeBundle(
            points=points,
            remaining=list(points),
            initial_radius_m=float(circle["radius"]),
            kind=kind or "unknown",
        )
        state.probe_bundles[track.channel] = bundle
        state.probe_bundle_counts[track.channel] = (
            state.probe_bundle_counts.get(track.channel, 0)+1
        )
        track.probe_points = list(points)
        state.probe_diagnostics.append({
            "event": "bundle_started",
            "channel": track.channel,
            "bundle_index": state.probe_bundle_counts[track.channel],
            "kind": bundle.kind,
            "radius_m": circle["radius"],
            "points": list(points),
        })
        return bundle

    def _select_probe_point(self, state, track, bundle):
        belief = state.joint_beliefs.get(track.channel)

        def key(point):
            visible_weight = (
                belief.visible_weight(point)
                if belief is not None and belief.scenarios else 0.0
            )
            action_time = measure_cost(
                state.position, point, state.current_channel, track.channel,
            ).total_s
            return (-visible_weight, action_time, point)

        return min(bundle.remaining, key=key)

    def _continuation_points(self, state, track):
        return [
            tuple(other.region["minimum_enclosing_circle"]["center"])
            for channel, other in sorted(state.sources.items())
            if (channel != track.channel and channel not in state.cleared
                and other.region is not None
                and other.region.get("status") == "bounded")
        ]

    def _evaluate_probe_decision(self, state, track, points, *,
                                 remaining_clear_points=None,
                                 risk_metric=None, savings_margin_s=None,
                                 candidate_limit=None,
                                 one_step_replan=False):
        try:
            belief = state.joint_beliefs.get(track.channel)
            if belief is None:
                belief = self._refresh_belief(state, track)
            decision = evaluate_directional_probe_decision(
                track, belief, points,
                current_position=state.position,
                current_channel=state.current_channel,
                config=self.q2_config,
                continuation_points=self._continuation_points(state, track),
                remaining_clear_points=remaining_clear_points,
                savings_margin_s=(
                    self.directional_rolling_savings_margin_s
                    if savings_margin_s is None else savings_margin_s
                ),
                risk_metric=(
                    self.directional_rolling_risk_metric
                    if risk_metric is None else risk_metric
                ),
                cvar_alpha=self.directional_rolling_cvar_alpha,
                scenario_limit=self.directional_rolling_scenario_limit,
                candidate_limit=(
                    self.directional_rolling_candidate_limit
                    if candidate_limit is None else candidate_limit
                ),
                cpu_time_limit_s=self.directional_rolling_cpu_time_limit_s,
                one_step_replan=one_step_replan,
            )
        except (RuntimeError, ValueError, KeyError, ZeroDivisionError) as error:
            decision = {
                "decision": "clear",
                "solver_status": "fallback",
                "timed_out": False,
                "reason": f"evaluation_error:{type(error).__name__}",
                "estimated_saving_s": 0.0,
            }
        return decision

    def _record_rolling_decision(self, state, track, decision):
        track.rolling_decision_count += 1
        track.last_rolling_decision = decision
        state.rolling_diagnostics.append({
            "event": "directional_rolling_decision",
            "channel": track.channel,
            **decision,
        })
        if decision["decision"] == "measure":
            track.rolling_measure_count += 1
        return decision

    def _rolling_probe_decision(self, state, track, points, *,
                                remaining_clear_points=None,
                                risk_metric=None, savings_margin_s=None,
                                candidate_limit=None,
                                one_step_replan=False):
        decision = self._evaluate_probe_decision(
            state, track, points,
            remaining_clear_points=remaining_clear_points,
            risk_metric=risk_metric,
            savings_margin_s=savings_margin_s,
            candidate_limit=candidate_limit,
            one_step_replan=one_step_replan,
        )
        return self._record_rolling_decision(state, track, decision)

    def _prepare_directional_clear(self, state, track, reason):
        track.refinement_stopped = True
        state.probe_diagnostics.append({
            "event": "fallback_to_posterior_clear",
            "channel": track.channel,
            "reason": reason,
            "radius_m": track.region["minimum_enclosing_circle"]["radius"],
        })
        return self._prepare_direct_clear(state, track)

    @staticmethod
    def _remaining_clear_points(track):
        if not track.fallback_points:
            return None
        return track.fallback_points[track.fallback_index:]

    def _single_source_action(self, state, track):
        bundle = state.probe_bundles.get(track.channel)
        initial_selected_point = None
        if bundle is None:
            if not self._can_refine(track, state):
                return self._prepare_directional_clear(
                    state, track, "probe_bundle_limit",
                )
            try:
                points, kind = self._probe_points(state, track)
            except (RuntimeError, ValueError, KeyError):
                return self._prepare_directional_clear(
                    state, track, "no_certified_probe_bundle",
                )
            if self.directional_rolling_mode == "scenario":
                decision = self._rolling_probe_decision(
                    state, track, points,
                )
                if decision["decision"] != "measure":
                    track.refinement_stopped = True
                    return self._prepare_directional_clear(
                        state, track, "rolling_selected_clear",
                    )
                initial_selected_point = tuple(decision["selected_point"])
            bundle = self._start_probe_bundle(
                state, track, points=points, kind=kind,
            )
            if bundle is None:
                return self._prepare_directional_clear(
                    state, track, "empty_certified_probe_bundle",
                )
        if not bundle.remaining:
            track.certificate_failed = True
            state.probe_bundles.pop(track.channel, None)
            return self._prepare_directional_clear(
                state, track, "probe_certificate_exhausted",
            )
        if initial_selected_point is not None:
            point = initial_selected_point
        elif self.directional_rolling_mode == "scenario":
            decision = self._rolling_probe_decision(
                state, track, bundle.remaining,
                remaining_clear_points=self._remaining_clear_points(track),
            )
            if decision["decision"] != "measure":
                state.probe_bundles.pop(track.channel, None)
                track.refinement_stopped = True
                return self._prepare_directional_clear(
                    state, track, "rolling_stopped_probe_bundle",
                )
            point = tuple(decision["selected_point"])
        else:
            point = self._select_probe_point(state, track, bundle)
        bundle.pending_point = point
        return self._action(
            state, "measure", point, track.channel, "directional_probe",
        )

    def _failed_clear_remeasure_action(self, state, track):
        """Q4 gate: same-position measurement may include no-signal."""
        if not track.fallback_remeasure_pending:
            return None
        track.fallback_remeasure_pending = False
        track.fallback_remeasure_checks += 1
        if self.failed_clear_remeasure_mode == "off":
            track.last_fallback_remeasure_decision = {
                "worthwhile": False, "reason": "mode_off",
            }
            return None
        remaining = track.fallback_points[track.fallback_index:]
        reason = None
        if (track.fallback_remeasure_count
                >= self.max_failed_clear_remeasures_per_source):
            reason = "remeasure_limit"
        elif len(remaining) < self.min_remaining_clear_points_for_remeasure:
            reason = "too_few_clear_points"
        elif any(self._same_point(state.position, point)
                 for point in track.fallback_remeasure_points):
            reason = "point_already_remeasured"
        elif any(self._same_point(state.position, item.position)
                 for item in state.measure_history.get(track.channel, ())):
            reason = "point_already_observed"
        elif (not track.observations
              or math.dist(state.position, track.observations[-1].position)
              < self.min_remeasure_baseline_m):
            reason = "insufficient_baseline"
        if reason is not None:
            track.last_fallback_remeasure_decision = {
                "worthwhile": False, "reason": reason,
            }
            return None
        decision = self._rolling_probe_decision(
            state, track, [state.position],
            remaining_clear_points=remaining,
            risk_metric="mean",
            savings_margin_s=self.failed_clear_measure_margin_s,
            candidate_limit=1,
        )
        decision = {
            **decision,
            "worthwhile": decision["decision"] == "measure",
        }
        track.last_fallback_remeasure_decision = decision
        if not decision["worthwhile"]:
            return None
        return self._action(
            state, "measure", state.position, track.channel,
            "fallback_remeasure",
        )

    def _start_selected_probe(self, state, track, points, kind, decision,
                              *, rescue=False):
        bundle = self._start_probe_bundle(
            state, track, points=points, kind=kind,
        )
        if bundle is None:
            return None
        point = tuple(decision["selected_point"])
        bundle.pending_point = point
        if rescue:
            state.rescue_probe_channels.add(track.channel)
            state.long_clear_diagnostics.append({
                "event": "long_clear_rescue_started",
                "channel": track.channel,
                "failed_clear_count": len(track.failed_clear_points),
                "point": point,
                "decision": decision,
            })
        return self._action(
            state, "measure", point, track.channel, "directional_probe",
        )

    def _long_clear_rescue_action(self, state, track):
        if self.long_clear_tail_mode != "adaptive":
            return None
        failure_count = len(track.failed_clear_points)
        if failure_count < self.long_clear_rescue_failure_threshold:
            return None
        if (state.long_clear_rescue_counts.get(track.channel, 0)
                >= self.max_long_clear_rescues_per_source):
            return None
        if (state.probe_bundle_counts.get(track.channel, 0)
                >= self.max_refinements or track.certificate_failed):
            return None
        remaining = self._remaining_clear_points(track)
        if not remaining:
            return None
        state.long_clear_rescue_counts[track.channel] = (
            state.long_clear_rescue_counts.get(track.channel, 0)+1
        )
        try:
            points, kind = self._probe_points(state, track)
            decision = self._rolling_probe_decision(
                state, track, points,
                remaining_clear_points=remaining,
                risk_metric="mean",
                one_step_replan=True,
            )
        except (RuntimeError, ValueError, KeyError):
            return None
        state.long_clear_diagnostics.append({
            "event": "long_clear_rescue_checked",
            "channel": track.channel,
            "failed_clear_count": failure_count,
            "decision": decision,
        })
        if decision["decision"] != "measure":
            return None
        track.refinement_stopped = False
        return self._start_selected_probe(
            state, track, points, kind, decision, rescue=True,
        )

    def _route_service_spec(self, state, track):
        channel = track.channel
        circle = track.region["minimum_enclosing_circle"]
        source_version = self._source_version(track)
        if circle["radius"] <= 19.9 and not track.certificate_failed:
            center = tuple(circle["center"])
            return SourceServiceSpec(
                channel=channel, mode="certified_clear",
                entry_point=center, entry_action_kind="clear",
                entry_action_channel=channel, route_points=(center,),
                source_version=source_version,
                reorder_clear_points=False,
                diagnostics={"radius_m": circle["radius"]},
            )

        if track.fallback_points:
            clear_points = tuple(
                track.fallback_points[track.fallback_index:]
            )
            return SourceServiceSpec(
                channel=channel, mode="direct_clear", entry_point=None,
                entry_action_kind="clear", entry_action_channel=channel,
                route_points=clear_points, source_version=source_version,
                reorder_clear_points=False,
                diagnostics={"existing_fallback": True},
            )

        raw_clear_points = tuple(
            self._cached_posterior_clear_points(track.region)
        )
        return SourceServiceSpec(
            channel=channel, mode="direct_clear", entry_point=None,
            entry_action_kind="clear", entry_action_channel=channel,
            route_points=raw_clear_points, source_version=source_version,
            reorder_clear_points=True,
            diagnostics={
                "radius_m": circle["radius"],
                "prediction": "conservative_clear_service",
            },
        )

    def _q4_route_resolve_choice(self, state, remaining):
        try:
            specs = {
                channel: self._route_service_spec(
                    state, state.sources[channel],
                )
                for channel in remaining
            }
            route_plan = plan_service_route(
                specs, state.position, state.current_channel,
                cpu_time_limit_s=self.route_cpu_time_limit_s,
                max_2opt_iterations=self.route_max_2opt_iterations,
            )
        except (RuntimeError, ValueError, KeyError) as error:
            route_plan = None
            self.route_planning_history.append({
                "status": "error",
                "reason": f"{type(error).__name__}:{error}",
                "cpu_wall_time_s": 0.0,
                "order": [],
                "predicted_total_cost_s": None,
                "predicted_first_block_cost_s": None,
            })
        if route_plan is None or route_plan.estimate is None:
            if route_plan is not None:
                self._record_route_plan(route_plan)
            action = self._legacy_resolve_choice(state, remaining)
            if action is not None:
                # Even if the bounded route solver cannot return a usable
                # order, finish the fallback-selected source as one service
                # block instead of paying the same failed planning cost again
                # after every measurement on that source.
                state.route_active_channel = action.channel
            return action

        self._record_route_plan(route_plan)
        selected_channel = route_plan.estimate.order[0]
        state.route_active_channel = selected_channel
        selected_spec = specs[selected_channel]
        track = state.sources[selected_channel]
        if selected_spec.mode == "certified_clear":
            return self._action(
                state, "clear", selected_spec.entry_point,
                selected_channel, "certified_clear",
            )
        return self._single_source_action(state, track)

    def _resolve_action(self, state, *, allow_exit=True):
        remaining = [
            channel for channel in sorted(state.sources)
            if channel not in state.cleared
        ]
        if not remaining:
            if not allow_exit:
                return None
            if state.cleared | state.absent != set(range(1, 21)):
                raise RuntimeError("频道终止证书不完整。")
            state.phase = "exit"
            return None

        for channel in remaining:
            track = state.sources[channel]
            if not track.fallback_remeasure_pending:
                continue
            action = self._failed_clear_remeasure_action(state, track)
            if action is not None:
                return action
        for channel in remaining:
            if channel in state.probe_bundles:
                return self._single_source_action(
                    state, state.sources[channel],
                )
        for channel in remaining:
            action = self._long_clear_rescue_action(
                state, state.sources[channel],
            )
            if action is not None:
                return action

        if (self.multi_source_route_mode == "insertion_2opt"
                and state.route_active_channel in remaining):
            return self._single_source_action(
                state, state.sources[state.route_active_channel],
            )

        active_fallbacks = [
            state.sources[channel] for channel in remaining
            if (state.sources[channel].fallback_points
                and state.sources[channel].fallback_index
                < len(state.sources[channel].fallback_points))
        ]
        if active_fallbacks:
            track = min(active_fallbacks, key=lambda item: (
                math.dist(
                    state.position,
                    item.fallback_points[item.fallback_index],
                ),
                item.channel,
            ))
            return self._prepare_direct_clear(state, track)

        if self.multi_source_route_mode == "insertion_2opt":
            return self._q4_route_resolve_choice(state, remaining)

        certified = []
        for channel in remaining:
            track = state.sources[channel]
            circle = track.region["minimum_enclosing_circle"]
            if circle["radius"] <= 19.9 and not track.certificate_failed:
                certified.append((tuple(circle["center"]), channel))
        if certified:
            center, channel = min(
                certified,
                key=lambda item: (math.dist(state.position, item[0]), item[1]),
            )
            return self._action(
                state, "clear", center, channel, "certified_clear",
            )
        return self._legacy_resolve_choice(state, remaining)

    def apply_response(self, state, action, response):
        mode = state.pending_mode
        old_radius = None
        if action.kind == "measure" and action.channel in state.sources:
            region = state.sources[action.channel].region
            if region is not None:
                old_radius = region["minimum_enclosing_circle"]["radius"]

        super().apply_response(state, action, response)

        if action.kind == "measure":
            history = state.measure_history.setdefault(action.channel, [])
            history.append(self._measurement_record(action, response))
            track = state.sources.get(action.channel)
            if track is not None and track.region is not None:
                self._refresh_belief(state, track)
                if (response["measure_result"] == "direction"
                        and track.fallback_points):
                    if mode == "directional_probe":
                        self._rebuild_fallback_after_remeasure(state, track)

            if mode == "directional_probe" and track is not None:
                bundle = state.probe_bundles.get(action.channel)
                if bundle is not None:
                    point = tuple(action.position)
                    bundle.remaining = [
                        candidate for candidate in bundle.remaining
                        if not self._same_point(candidate, point)
                    ]
                    bundle.pending_point = None
                    result = response["measure_result"]
                    bundle.outcomes.append(result)
                    state.probe_diagnostics.append({
                        "event": "probe_result",
                        "channel": action.channel,
                        "point": point,
                        "result": result,
                        "remaining_count": len(bundle.remaining),
                        "belief": (
                            state.joint_beliefs[action.channel].summary()
                            if action.channel in state.joint_beliefs else None
                        ),
                    })
                    if result in ("direction", "near"):
                        if result == "direction":
                            track.refinements += 1
                            new_radius = track.region[
                                "minimum_enclosing_circle"
                            ]["radius"]
                            if old_radius is not None and old_radius > 0.0:
                                improvement = max(
                                    0.0, (old_radius-new_radius)/old_radius,
                                )
                                track.last_improvement_ratio = improvement
                                if improvement < self.min_improvement_ratio:
                                    track.stagnant_refinements += 1
                                else:
                                    track.stagnant_refinements = 0
                                if (track.stagnant_refinements
                                        >= self.stagnation_limit):
                                    track.refinement_stopped = True
                        state.probe_bundles.pop(action.channel, None)
                    elif not bundle.remaining:
                        track.certificate_failed = True
                        track.refinement_stopped = True
                        state.probe_bundles.pop(action.channel, None)
                        state.probe_diagnostics.append({
                            "event": "certificate_failed",
                            "channel": action.channel,
                            "points": list(bundle.points),
                            "outcomes": list(bundle.outcomes),
                        })
                if action.channel in state.rescue_probe_channels:
                    state.rescue_probe_channels.discard(action.channel)
                    if response["measure_result"] == "no_signal":
                        state.probe_bundles.pop(action.channel, None)
                        track.refinement_stopped = True
            return

        if action.kind == "clear":
            track = state.sources.get(action.channel)
            if response.get("clear_result") == "success":
                state.probe_bundles.pop(action.channel, None)
                if state.route_active_channel == action.channel:
                    state.route_active_channel = None
            elif (mode == "fallback_clear" and track is not None
                  and track.region is not None):
                # The continuous polygon is intentionally unchanged; the
                # finite ranking belief may safely discard sampled positions
                # inside a failed 20 m optical-clear disk.
                self._refresh_belief(state, track)
