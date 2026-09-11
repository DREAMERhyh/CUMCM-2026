"""Finite offline baseline state machine for omnidirectional sources."""

from dataclasses import dataclass, field
import math

from common.domain import build_region_from_observations
from common.models import Action, BearingObservation
from q2.planner import Q2Config, plan_measurement
from .adaptive import (measurement_is_worthwhile, nearest_neighbor_order,
                       posterior_clear_points, worst_case_clear_cost)
from .coverage import ring7, strip_clear_points
from .fallback_remeasure import evaluate_failed_clear_remeasure
from .joint import (direct_clear_cost, fixed_point_evaluation,
                    marginal_saving, predicted_clear_cost)
from .rolling_time import evaluate_total_time_decision


@dataclass
class SourceTrack:
    channel: int
    observations: list[BearingObservation] = field(default_factory=list)
    region: dict | None = None
    refinements: int = 0
    fallback_points: list[tuple[float, float]] = field(default_factory=list)
    fallback_index: int = 0
    certificate_failed: bool = False
    probe_points: list[tuple[float, float]] = field(default_factory=list)
    stagnant_refinements: int = 0
    last_improvement_ratio: float | None = None
    failed_clear_points: list[tuple[float, float]] = field(default_factory=list)
    refinement_stopped: bool = False
    opportunistic_measurements: int = 0
    failed_clear_disks: list[tuple[tuple[float, float], float]] = field(
        default_factory=list
    )
    fallback_remeasure_count: int = 0
    fallback_remeasure_checks: int = 0
    fallback_remeasure_points: list[tuple[float, float]] = field(
        default_factory=list
    )
    fallback_remeasure_pending: bool = False
    last_fallback_remeasure_decision: dict | None = None
    rolling_decision_count: int = 0
    rolling_measure_count: int = 0
    last_rolling_decision: dict | None = None


@dataclass
class Q3State:
    entered: bool = False
    exited: bool = False
    position: tuple[float, float] = (0.0, 0.0)
    current_channel: int = 1
    virtual_time_s: float = 0.0
    scan_point_index: int = 0
    scan_order: list[int] = field(default_factory=list)
    scan_channel_index: int = 0
    scan_batch_order: list[int] = field(default_factory=list)
    scan_batch_index: int = 0
    scan_batch_prepared: bool = False
    phase: str = "scan"
    sources: dict[int, SourceTrack] = field(default_factory=dict)
    cleared: set[int] = field(default_factory=set)
    absent: set[int] = field(default_factory=set)
    forced_clear: tuple[tuple[float, float], int] | None = None
    pending: Action | None = None
    pending_mode: str | None = None
    sequence: int = 0
    batch_point: tuple[float, float] | None = None
    batch_channels: list[int] = field(default_factory=list)
    batch_index: int = 0
    batch_target_channel: int | None = None


class Q3Policy:
    def __init__(self, *, max_refinements=5, error_deg=1.005,
                 coverage_points=None, fim_cpu_time_limit_s=10.0,
                 adaptive_refinement=True, posterior_grid=True,
                 min_improvement_ratio=0.05, stagnation_limit=2,
                 measure_savings_margin_s=10.0,
                 prefer_continuous_fim=True,
                 joint_batch_mode="guaranteed",
                 batch_savings_margin_s=2.0,
                 max_opportunistic_per_source=2,
                 failed_clear_remeasure_mode="gated",
                 max_failed_clear_remeasures_per_source=3,
                 min_remaining_clear_points_for_remeasure=3,
                 min_remeasure_baseline_m=40.0,
                 failed_clear_measure_margin_s=2.0,
                 rolling_time_mode="scenario",
                 rolling_scenario_limit=4,
                 rolling_candidate_limit=12,
                 rolling_risk_metric="cvar",
                 rolling_cvar_alpha=0.9,
                 rolling_cpu_time_limit_s=0.2):
        if fim_cpu_time_limit_s <= 0:
            raise ValueError("FIM真实计算时限必须为正数。")
        if max_refinements < 0:
            raise ValueError("细化次数不能为负。")
        if not 0.0 <= min_improvement_ratio < 1.0:
            raise ValueError("停滞阈值必须位于[0,1)区间。")
        if stagnation_limit < 1 or measure_savings_margin_s < 0.0:
            raise ValueError("停滞次数至少为1，节省余量不能为负。")
        if joint_batch_mode not in ("off", "guaranteed", "all_active"):
            raise ValueError("联合批测模式必须为off、guaranteed或all_active。")
        if batch_savings_margin_s < 0.0:
            raise ValueError("批测节省余量不能为负。")
        if max_opportunistic_per_source < 0:
            raise ValueError("每源顺便批测上限不能为负。")
        if failed_clear_remeasure_mode not in ("off", "gated"):
            raise ValueError("清除失败复测模式必须为off或gated。")
        if max_failed_clear_remeasures_per_source < 0:
            raise ValueError("每源清除失败复测上限不能为负。")
        if min_remaining_clear_points_for_remeasure < 1:
            raise ValueError("复测所需剩余清除点数至少为1。")
        if min_remeasure_baseline_m < 0.0 or failed_clear_measure_margin_s < 0.0:
            raise ValueError("复测基线和节省余量不能为负。")
        if rolling_time_mode not in ("off", "scenario"):
            raise ValueError("滚动总时间模式必须为off或scenario。")
        if rolling_scenario_limit < 1 or rolling_candidate_limit < 1:
            raise ValueError("滚动场景数和候选数上限至少为1。")
        if rolling_risk_metric not in ("p90", "cvar", "worst", "mean"):
            raise ValueError("滚动风险指标必须为p90、cvar、worst或mean。")
        if not 0.0 < rolling_cvar_alpha < 1.0:
            raise ValueError("滚动CVaR分位必须位于(0,1)。")
        if rolling_cpu_time_limit_s <= 0.0:
            raise ValueError("滚动评价CPU时限必须为正数。")
        self.coverage_points = list(coverage_points or ring7())
        self.max_refinements = max_refinements
        self.error_deg = error_deg
        self.adaptive_refinement = adaptive_refinement
        self.posterior_grid = posterior_grid
        self.min_improvement_ratio = min_improvement_ratio
        self.stagnation_limit = stagnation_limit
        self.measure_savings_margin_s = measure_savings_margin_s
        self.prefer_continuous_fim = prefer_continuous_fim
        self.joint_batch_mode = joint_batch_mode
        self.batch_savings_margin_s = batch_savings_margin_s
        self.max_opportunistic_per_source = max_opportunistic_per_source
        self.failed_clear_remeasure_mode = failed_clear_remeasure_mode
        self.max_failed_clear_remeasures_per_source = (
            max_failed_clear_remeasures_per_source
        )
        self.min_remaining_clear_points_for_remeasure = (
            min_remaining_clear_points_for_remeasure
        )
        self.min_remeasure_baseline_m = min_remeasure_baseline_m
        self.failed_clear_measure_margin_s = failed_clear_measure_margin_s
        self.rolling_time_mode = rolling_time_mode
        self.rolling_scenario_limit = rolling_scenario_limit
        self.rolling_candidate_limit = rolling_candidate_limit
        self.rolling_risk_metric = rolling_risk_metric
        self.rolling_cvar_alpha = rolling_cvar_alpha
        self.rolling_cpu_time_limit_s = rolling_cpu_time_limit_s
        self.q2_config = Q2Config(error_deg=error_deg, circle_sides=16,
                                  scenario_limit=4,
                                  continuous_fim_enabled=True,
                                  fim_cpu_time_limit_s=fim_cpu_time_limit_s,
                                  near_optimal_region_mode="off")

    def initial_state(self):
        return Q3State()

    def _action(self, state, kind, position=None, channel=None, mode=None):
        state.sequence += 1
        state.pending = Action(kind, f"{kind}-{state.sequence}", position, channel)
        state.pending_mode = mode
        return state.pending

    def _can_refine(self, track):
        return (
            track.refinements < self.max_refinements
            and track.stagnant_refinements < self.stagnation_limit
            and not track.refinement_stopped
        )

    def _can_batch(self, track):
        return (
            track.opportunistic_measurements
            < self.max_opportunistic_per_source
            and not track.refinement_stopped
            and not track.certificate_failed
            and track.region["minimum_enclosing_circle"]["radius"] > 19.9
        )

    @staticmethod
    def _same_point(first, second, tolerance=1e-7):
        return (abs(first[0]-second[0]) <= tolerance
                and abs(first[1]-second[1]) <= tolerance)

    def _include_batch_evaluation(self, evaluation, saving_s):
        if self.joint_batch_mode == "all_active":
            return True
        return (evaluation["guaranteed_reception"]
                and saving_s > self.batch_savings_margin_s)

    def _prepare_scan_batch(self, state, point):
        if self.joint_batch_mode == "off":
            return []
        entries = []
        for channel, track in sorted(state.sources.items()):
            if channel in state.cleared or not self._can_batch(track):
                continue
            if self._same_point(track.observations[-1].position, point):
                continue
            clear_now_s, _ = direct_clear_cost(track.region, point)
            evaluation = fixed_point_evaluation(
                track, point,
                current_channel=state.current_channel,
                config=self.q2_config,
            )
            radius = track.region["minimum_enclosing_circle"]["radius"]
            saving_s = marginal_saving(clear_now_s, radius, evaluation)
            if self._include_batch_evaluation(evaluation, saving_s):
                entries.append((channel, saving_s))
        entries.sort(key=lambda item: (-item[1], item[0]))
        return [channel for channel, _ in entries]

    def _scan_action(self, state):
        while state.scan_point_index < len(self.coverage_points):
            point = self.coverage_points[state.scan_point_index]
            if not state.scan_order:
                state.scan_order = [state.current_channel] + [
                    channel for channel in range(1, 21)
                    if channel != state.current_channel
                ]
                state.scan_channel_index = 0
            while state.scan_channel_index < len(state.scan_order):
                channel = state.scan_order[state.scan_channel_index]
                if channel in state.cleared or channel in state.sources:
                    state.scan_channel_index += 1
                    continue
                return self._action(state, "measure",
                                    point,
                                    channel, "scan")
            if not state.scan_batch_prepared:
                state.scan_batch_order = self._prepare_scan_batch(state, point)
                state.scan_batch_index = 0
                state.scan_batch_prepared = True
            while state.scan_batch_index < len(state.scan_batch_order):
                channel = state.scan_batch_order[state.scan_batch_index]
                if channel in state.cleared:
                    state.scan_batch_index += 1
                    continue
                return self._action(state, "measure", point, channel,
                                    "scan_batch")
            state.scan_point_index += 1
            state.scan_order = []
            state.scan_batch_order = []
            state.scan_batch_index = 0
            state.scan_batch_prepared = False
        state.absent = set(range(1, 21))-set(state.sources)-state.cleared
        state.phase = "resolve"
        return None

    def _refinement_plan(self, state, track):
        return plan_measurement(
            track.region, track.observations,
            current_position=state.position,
            current_channel=state.current_channel,
            target_channel=track.channel,
            config=self.q2_config,
        )

    def _refinement_candidate(self, plan):
        continuous = plan["continuous_fim"]
        if self.prefer_continuous_fim and continuous.get("status") == "ok":
            return continuous["selected"]
        return plan["selected"]

    def _refinement_point(self, state, track):
        plan = self._refinement_plan(state, track)
        return tuple(self._refinement_candidate(plan)["point"])

    def _rolling_decision(self, state, track, plan):
        """Evaluate task two without changing any Q2 return structure."""
        continuation_points = [
            tuple(other.region["minimum_enclosing_circle"]["center"])
            for channel, other in sorted(state.sources.items())
            if (channel != track.channel and channel not in state.cleared
                and other.region is not None
                and other.region.get("status") == "bounded")
        ]
        try:
            decision = evaluate_total_time_decision(
                track,
                plan,
                current_position=state.position,
                current_channel=state.current_channel,
                config=self.q2_config,
                savings_margin_s=self.measure_savings_margin_s,
                scenario_limit=self.rolling_scenario_limit,
                candidate_limit=self.rolling_candidate_limit,
                cvar_alpha=self.rolling_cvar_alpha,
                risk_metric=self.rolling_risk_metric,
                cpu_time_limit_s=self.rolling_cpu_time_limit_s,
                continuation_points=continuation_points,
            )
        except (RuntimeError, ValueError, KeyError, ZeroDivisionError) as error:
            decision = {
                "decision": "clear",
                "solver_status": "fallback",
                "timed_out": False,
                "reason": f"evaluation_error:{type(error).__name__}",
                "estimated_saving_s": 0.0,
            }
        track.rolling_decision_count += 1
        track.last_rolling_decision = decision
        if decision["decision"] == "measure":
            track.rolling_measure_count += 1
        return decision

    def _joint_plan(self, state, remaining):
        clear_costs = {}
        rejected = set()

        def clear_cost(channel):
            if channel not in clear_costs:
                clear_costs[channel] = direct_clear_cost(
                    state.sources[channel].region, state.position
                )[0]
            return clear_costs[channel]

        options = []
        # Compare every worthwhile target so movement between sources becomes
        # part of the multi-source route instead of following channel order.
        refinable = [channel for channel in remaining
                     if self._can_refine(state.sources[channel])]
        for target_channel in refinable:
            target = state.sources[target_channel]
            radius = target.region["minimum_enclosing_circle"]["radius"]
            try:
                q2_plan = self._refinement_plan(state, target)
            except (RuntimeError, ValueError):
                rejected.add(target_channel)
                continue
            if self.rolling_time_mode == "scenario":
                decision = self._rolling_decision(state, target, q2_plan)
                if decision["decision"] != "measure":
                    rejected.add(target_channel)
                    continue
                candidate = {
                    "point": decision["selected_point"],
                    "action_time_s": decision["measure_action_time_s"],
                }
                target_saving = decision["estimated_saving_s"]
            else:
                candidate = self._refinement_candidate(q2_plan)
                target_future = predicted_clear_cost(
                    clear_cost(target_channel), radius,
                    candidate["worst_case_radius_m"],
                )
                target_saving = (clear_cost(target_channel)
                                 - candidate["action_time_s"]
                                 - target_future)
            if target_saving <= self.measure_savings_margin_s:
                rejected.add(target_channel)
                continue

            point = tuple(candidate["point"])
            entries = [(target_channel, target_saving)]
            for channel in remaining:
                if channel == target_channel:
                    continue
                track = state.sources[channel]
                if not self._can_batch(track):
                    continue
                if self._same_point(track.observations[-1].position, point):
                    continue
                evaluation = fixed_point_evaluation(
                    track, point,
                    current_channel=target_channel,
                    config=self.q2_config,
                )
                other_radius = track.region[
                    "minimum_enclosing_circle"
                ]["radius"]
                saving_s = marginal_saving(
                    clear_cost(channel), other_radius, evaluation
                )
                if self._include_batch_evaluation(evaluation, saving_s):
                    entries.append((channel, saving_s))
            extra = sorted(entries[1:], key=lambda item: (-item[1], item[0]))
            entries = [entries[0], *extra]
            options.append({
                "point": point,
                "channels": [channel for channel, _ in entries],
                "target_channel": target_channel,
                "estimated_saving_s": sum(value for _, value in entries),
                "target_action_time_s": candidate["action_time_s"],
            })
        if not options:
            return None, rejected
        best = min(options, key=lambda item: (
            item["target_action_time_s"],
            -len(item["channels"]),
            -item["estimated_saving_s"],
            item["target_channel"],
        ))
        return best, rejected-set(best["channels"])

    def _start_joint_batch(self, state, plan):
        state.batch_point = tuple(plan["point"])
        state.batch_channels = list(plan["channels"])
        state.batch_index = 0
        state.batch_target_channel = plan["target_channel"]

    def _next_joint_batch_action(self, state):
        while state.batch_index < len(state.batch_channels):
            channel = state.batch_channels[state.batch_index]
            track = state.sources.get(channel)
            is_target = channel == state.batch_target_channel
            eligible = (self._can_refine(track) if is_target and track
                        else self._can_batch(track) if track else False)
            if channel in state.cleared or track is None or not eligible:
                state.batch_index += 1
                continue
            return self._action(state, "measure", state.batch_point,
                                channel,
                                "joint_target" if is_target else "joint_extra")
        state.batch_point = None
        state.batch_channels = []
        state.batch_index = 0
        state.batch_target_channel = None
        return None

    def _failed_clear_remeasure_action(self, state, track):
        """Evaluate exactly once after a failed fallback clear."""
        if not track.fallback_remeasure_pending:
            return None
        track.fallback_remeasure_pending = False
        track.fallback_remeasure_checks += 1
        if self.failed_clear_remeasure_mode == "off":
            track.last_fallback_remeasure_decision = {
                "worthwhile": False,
                "reason": "mode_off",
            }
            return None
        remaining_points = track.fallback_points[track.fallback_index:]
        try:
            decision = evaluate_failed_clear_remeasure(
                track,
                state.position,
                remaining_points,
                current_channel=state.current_channel,
                config=self.q2_config,
                max_remeasures=self.max_failed_clear_remeasures_per_source,
                min_remaining_points=(
                    self.min_remaining_clear_points_for_remeasure
                ),
                min_baseline_m=self.min_remeasure_baseline_m,
                savings_margin_s=self.failed_clear_measure_margin_s,
            )
        except (RuntimeError, ValueError, KeyError) as error:
            decision = {
                "worthwhile": False,
                "reason": f"evaluation_error:{type(error).__name__}",
            }
        track.last_fallback_remeasure_decision = decision
        if not decision["worthwhile"]:
            return None
        return self._action(
            state, "measure", state.position, track.channel,
            "fallback_remeasure",
        )

    def _rebuild_fallback_after_remeasure(self, state, track):
        raw_points = posterior_clear_points(track.region)
        raw_points = [
            point for point in raw_points
            if not any(self._same_point(point, failed)
                       for failed in track.failed_clear_points)
        ]
        track.fallback_points = nearest_neighbor_order(
            raw_points, state.position
        )
        track.fallback_index = 0

    def _resolve_action(self, state, *, allow_exit=True):
        if state.batch_channels:
            action = self._next_joint_batch_action(state)
            if action is not None:
                return action
        remaining = [channel for channel in sorted(state.sources)
                     if channel not in state.cleared]
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
        certified = []
        for channel in remaining:
            candidate_track = state.sources[channel]
            circle = candidate_track.region["minimum_enclosing_circle"]
            if circle["radius"] <= 19.9 and not candidate_track.certificate_failed:
                center = tuple(circle["center"])
                certified.append((center, channel))
        if certified:
            center, channel = min(
                certified,
                key=lambda item: (math.dist(state.position, item[0]), item[1]),
            )
            return self._action(state, "clear", center, channel,
                                "certified_clear")
        if self.adaptive_refinement and self.joint_batch_mode != "off":
            plan, rejected = self._joint_plan(state, remaining)
            if plan is not None:
                for channel in rejected:
                    state.sources[channel].refinement_stopped = True
                self._start_joint_batch(state, plan)
                return self._next_joint_batch_action(state)
            for channel in rejected:
                state.sources[channel].refinement_stopped = True

        track = state.sources[remaining[0]]
        radius = track.region["minimum_enclosing_circle"]["radius"]
        can_refine = self._can_refine(track)
        if can_refine:
            if not self.adaptive_refinement:
                point = self._refinement_point(state, track)
                return self._action(state, "measure", point,
                                    track.channel, "refine")
            raw_points = posterior_clear_points(track.region)
            clear_now_s = worst_case_clear_cost(raw_points, state.position)
            try:
                plan = self._refinement_plan(state, track)
            except (RuntimeError, ValueError):
                if self.rolling_time_mode != "scenario":
                    raise
                plan = None
            if self.rolling_time_mode == "scenario":
                decision = (self._rolling_decision(state, track, plan)
                            if plan is not None else None)
                if decision is not None and decision["decision"] == "measure":
                    return self._action(
                        state, "measure", tuple(decision["selected_point"]),
                        track.channel, "refine",
                    )
            else:
                candidate = self._refinement_candidate(plan)
                if measurement_is_worthwhile(
                        radius,
                        candidate["worst_case_radius_m"],
                        candidate["action_time_s"],
                        margin_s=self.measure_savings_margin_s,
                        current_clear_cost_s=clear_now_s):
                    return self._action(state, "measure",
                                        tuple(candidate["point"]),
                                        track.channel, "refine")
            track.fallback_points = nearest_neighbor_order(
                raw_points, state.position
            )
            track.refinement_stopped = True
        if not track.fallback_points:
            if self.posterior_grid:
                raw_points = posterior_clear_points(track.region)
                track.fallback_points = nearest_neighbor_order(
                    raw_points, state.position
                )
            else:
                first = track.observations[0]
                track.fallback_points = list(strip_clear_points(
                    first.position, first.bearing_deg
                ))
        if track.fallback_index >= len(track.fallback_points):
            raise RuntimeError(f"频道{track.channel}有限清除保底耗尽。")
        return self._action(state, "clear",
                            track.fallback_points[track.fallback_index],
                            track.channel, "fallback_clear")

    def next_action(self, state):
        if state.pending is not None:
            return state.pending
        if not state.entered:
            return self._action(state, "enter", mode="enter")
        if state.forced_clear is not None:
            point, channel = state.forced_clear
            return self._action(state, "clear", point, channel, "near_clear")
        while True:
            if state.phase == "scan":
                action = self._scan_action(state)
                if action is not None:
                    return action
            elif state.phase == "resolve":
                action = self._resolve_action(state)
                if action is not None:
                    return action
            elif state.phase == "exit":
                return self._action(state, "exit", mode="exit")
            else:
                raise RuntimeError(f"未知策略阶段：{state.phase}")

    def _record_measurement(self, state, action, response, *, mode=None):
        result = response["measure_result"]
        if result == "near":
            state.forced_clear = (action.position, action.channel)
            return
        if result == "no_signal":
            return
        observation = BearingObservation(action.position, action.channel,
                                         "direction", response["svd_deg"])
        track = state.sources.setdefault(action.channel,
                                         SourceTrack(action.channel))
        old_radius = (track.region["minimum_enclosing_circle"]["radius"]
                      if track.region is not None else None)
        track.observations.append(observation)
        track.region = build_region_from_observations(
            track.observations, error_deg=self.error_deg, circle_sides=16)
        if (mode in ("refine", "joint_target")
                and old_radius is not None and old_radius > 0.0):
            new_radius = track.region["minimum_enclosing_circle"]["radius"]
            improvement = max(0.0, (old_radius-new_radius)/old_radius)
            track.last_improvement_ratio = improvement
            if improvement < self.min_improvement_ratio:
                track.stagnant_refinements += 1
            else:
                track.stagnant_refinements = 0

    def apply_response(self, state, action, response):
        if action != state.pending:
            raise RuntimeError("收到的响应与当前待处理动作不一致。")
        mode = state.pending_mode
        state.pending = None
        state.pending_mode = None
        if response.get("accepted") is not True:
            raise RuntimeError("离线客户端拒绝了动作。")
        state.virtual_time_s = float(response.get("virtual_time_s",
                                                  state.virtual_time_s))
        if action.kind == "enter":
            state.entered = True
            return
        if action.kind in ("measure", "clear"):
            state.position = action.position
        if action.kind == "measure":
            state.current_channel = action.channel
            self._record_measurement(state, action, response, mode=mode)
            if mode == "scan":
                state.scan_channel_index += 1
            elif mode == "scan_batch":
                state.scan_batch_index += 1
                state.sources[action.channel].opportunistic_measurements += 1
            elif mode == "joint_extra":
                state.batch_index += 1
                state.sources[action.channel].opportunistic_measurements += 1
            elif mode == "joint_target":
                state.batch_index += 1
                state.sources[action.channel].refinements += 1
                if response["measure_result"] == "no_signal":
                    state.sources[action.channel].stagnant_refinements += 1
            elif mode == "refine":
                state.sources[action.channel].refinements += 1
                if response["measure_result"] == "no_signal":
                    state.sources[action.channel].stagnant_refinements += 1
            elif mode == "fallback_remeasure":
                track = state.sources[action.channel]
                track.fallback_remeasure_count += 1
                track.fallback_remeasure_points.append(tuple(action.position))
                if response["measure_result"] == "direction":
                    self._rebuild_fallback_after_remeasure(state, track)
            return
        if action.kind == "clear":
            success = response["clear_result"] == "success"
            if success:
                state.cleared.add(action.channel)
                state.forced_clear = None
                return
            if mode == "near_clear":
                raise RuntimeError("near 后清除失败，规则或实现不一致。")
            track = state.sources.get(action.channel)
            if track is None:
                raise RuntimeError("对未发现频道执行了清除。")
            if mode == "certified_clear":
                track.certificate_failed = True
                track.refinements = self.max_refinements
            elif mode == "fallback_clear":
                point = tuple(action.position)
                track.failed_clear_points.append(point)
                track.failed_clear_disks.append((point, 20.0))
                track.fallback_index += 1
                track.fallback_remeasure_pending = True
            return
        if action.kind == "exit":
            state.exited = True

