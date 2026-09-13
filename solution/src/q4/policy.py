"""Q4 mixed-source policy built on the Q3 execution state machine.

本文件以 main 分支最新 q4 基线为骨架移植到 B2 分支，并把 B2 分支在
q1-q3 验证有效的思路融合注入：
- M9 近邻序（批量定位谱系，同池中位 -9.4%）：resolve 兜底按当前点→区域
  中心距离升序选源；
- A3 最优停止（guess_clear，q3 同池中位 -33%）：区域<=40m 先猜中心；
- TSPN 清除端点（|p-源|<=20 数学保证）：certified 清除朝下一目标偏移；
- probe_plan 蜂窝密排保底（轮6，tail 最坏 -906s）：clear_cover 默认
  probe_plan，数学上界 1+3k(k+1) 次清除；
- 鸽笼早停参数与 skip_low_value_refine（继承 B2 q3，扫描期交会价值跳测）；
- 批量解耦+全局 TSP 不引入（q4 定向源探测组为强交错结构，route 模块因
  B2 q3 无 q3.route 依赖而移除，main 默认本就 off）。
"""

from dataclasses import dataclass, field
import math

from common.time_model import measure_cost
from q3.coverage import probe_plan, strip_clear_points
from q3.policy import Q3Policy, Q3State

from .belief import Q4Measurement, build_joint_belief
from .directional import (adaptive_four_sided_points,
                          certified_probe_points, grid121, triangular25,
                          triangular37)
from .rolling import (evaluate_directional_probe_decision,
                      nearest_neighbor_order, posterior_clear_points)


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


class Q4Policy(Q3Policy):
    """Certified mixed omni/directional search with finite belief ranking.

    ``max_refinements`` counts started certified probe bundles, not individual
    probe points.  A bundle stops after ``direction``/``near``; after
    ``no_signal`` the Q4 rolling gate either retains the remaining certified
    points or switches to the independently certified posterior clear cover.
    """

    def __init__(self, *, max_refinements=2, error_deg=1.005,
                 fim_cpu_time_limit_s=6.0, scan_mode="triangular25",
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
                 use_optimal_stop=True,
                 guess_clear_threshold_m=40.0,
                 tspn_clear=True,
                 clear_cover="probe_plan",
                 pigeonhole_early_stop=False):
        if scan_mode not in (
                "triangular25", "triangular37", "grid121", "custom"):
            raise ValueError(
                "Q4扫描模式必须为triangular25、triangular37、grid121或custom。"
            )
        if coverage_points is not None:
            selected_coverage = list(coverage_points)
            scan_mode = "custom"
        elif scan_mode == "triangular25":
            selected_coverage = triangular25()
        elif scan_mode == "triangular37":
            selected_coverage = triangular37()
        elif scan_mode == "grid121":
            selected_coverage = grid121()
        else:
            raise ValueError("custom扫描模式必须显式提供coverage_points。")
        if clear_cover not in ("probe_plan", "posterior_grid", "strip"):
            raise ValueError("clear_cover 必须为probe_plan、posterior_grid或strip。")
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

        super().__init__(
            max_refinements=max_refinements,
            error_deg=error_deg,
            coverage_points=selected_coverage,
            fim_cpu_time_limit_s=fim_cpu_time_limit_s,
            use_optimal_stop=use_optimal_stop,
            guess_clear_threshold_m=guess_clear_threshold_m,
            pigeonhole_early_stop=pigeonhole_early_stop,
        )
        self.scan_mode = scan_mode
        self.tspn_clear = tspn_clear
        self.clear_cover = clear_cover
        # 停滞检测默认值内联（main 分支 q3.adaptive 的参数，B2 q3 无）
        self.min_improvement_ratio = 0.05
        self.stagnation_limit = 2
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
        self.failed_clear_remeasure_mode = failed_clear_remeasure_mode
        self.max_failed_clear_remeasures_per_source = (
            max_failed_clear_remeasures_per_source
        )
        self.min_remaining_clear_points_for_remeasure = (
            min_remaining_clear_points_for_remeasure
        )
        self.min_remeasure_baseline_m = min_remeasure_baseline_m
        self.failed_clear_measure_margin_s = failed_clear_measure_margin_s
        self.long_clear_rescue_failure_threshold = (
            long_clear_rescue_failure_threshold
        )
        self.max_long_clear_rescues_per_source = (
            max_long_clear_rescues_per_source
        )

    def initial_state(self):
        return Q4State()

    def _ensure_track_fields(self, track):
        """B2 分支 Q3Policy 的 SourceTrack 没有 main 版的扩展字段；
        探测组/补测/长尾/停滞逻辑需要的字段在此惰性初始化（不修改 q3）。"""
        defaults = {
            "refinement_stopped": False,
            "stagnant_refinements": 0,
            "last_improvement_ratio": None,
            "failed_clear_points": [],
            "failed_clear_disks": [],
            "fallback_remeasure_count": 0,
            "fallback_remeasure_checks": 0,
            "fallback_remeasure_points": [],
            "fallback_remeasure_pending": False,
            "last_fallback_remeasure_decision": None,
            "rolling_decision_count": 0,
            "rolling_measure_count": 0,
            "last_rolling_decision": None,
            "opportunistic_measurements": 0,
            "clear_guessed": False,
        }
        for name, value in defaults.items():
            if not hasattr(track, name):
                setattr(track, name, value)
        return track

    @staticmethod
    def _same_point(first, second, tolerance=1e-7):
        return (abs(first[0]-second[0]) <= tolerance
                and abs(first[1]-second[1]) <= tolerance)

    def _can_refine(self, track, state=None):
        track = self._ensure_track_fields(track)
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
        track = self._ensure_track_fields(track)
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
        track = self._ensure_track_fields(track)
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
        track = self._ensure_track_fields(track)
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
        track = self._ensure_track_fields(track)
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
        track = self._ensure_track_fields(track)
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

    def _prepare_direct_clear(self, state, track):
        """保底清除：按 clear_cover 生成有界点列并以近邻序逐点消除。"""
        track = self._ensure_track_fields(track)
        if not track.fallback_points:
            if self.clear_cover == "strip" or track.region is None:
                first = track.observations[0]
                track.fallback_points = list(strip_clear_points(
                    first.position, first.bearing_deg,
                ))
            else:
                points = (
                    probe_plan(track.region)
                    if self.clear_cover == "probe_plan"
                    else None
                )
                if not points and self.clear_cover == "posterior_grid":
                    try:
                        points = posterior_clear_points(track.region)
                    except ValueError:
                        points = None
                if not points:
                    # probe_plan/posterior_grid 退化时回退条带
                    first = track.observations[0]
                    points = list(strip_clear_points(
                        first.position, first.bearing_deg,
                    ))
                track.fallback_points = nearest_neighbor_order(
                    points, state.position,
                )
            track.fallback_index = 0
        if track.fallback_index >= len(track.fallback_points):
            raise RuntimeError(f"频道{track.channel}有限清除保底耗尽。")
        return self._action(
            state, "clear", track.fallback_points[track.fallback_index],
            track.channel, "fallback_clear",
        )

    def _rebuild_fallback_after_remeasure(self, state, track):
        """原地补测拿到新方向后，按当前保底模式重建清除点列。"""
        track = self._ensure_track_fields(track)
        if self.clear_cover == "strip":
            return
        try:
            raw = (
                probe_plan(track.region)
                if self.clear_cover == "probe_plan"
                else posterior_clear_points(track.region)
            )
        except ValueError:
            return
        if not raw:
            return
        track.fallback_points = nearest_neighbor_order(raw, state.position)
        track.fallback_index = 0

    def _nearest_remaining_channel(self, state, remaining):
        """M9 近邻序（B2 谱系）：按"当前点→区域中心"距离升序取第一源。"""
        def key(channel):
            track = state.sources[channel]
            if (track.region is None
                    or track.region.get("status") != "bounded"):
                return float("inf"), channel
            return (math.dist(state.position, tuple(
                track.region["minimum_enclosing_circle"]["center"])),
                channel)
        return min(remaining, key=key)

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
            track = self._ensure_track_fields(state.sources[channel])
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
            # TSPN 清除端点（B2 批量策略谱系，数学保证 |p-源|<=20）：在
            # 清除邻域边界朝下一个最近未处理源中心偏移，省后续跨源移动。
            if self.tspn_clear:
                radius = state.sources[channel].region[
                    "minimum_enclosing_circle"]["radius"]
                reach = max(0.0, 20.0-radius)
                best_other = None
                for other_channel in remaining:
                    if other_channel == channel:
                        continue
                    other = state.sources[other_channel]
                    if (other.region is None
                            or other.region.get("status") != "bounded"):
                        continue
                    other_center = tuple(other.region[
                        "minimum_enclosing_circle"]["center"])
                    distance = math.dist(center, other_center)
                    if distance <= 1e-9:
                        continue
                    if best_other is None or distance < best_other[0]:
                        best_other = (distance, other_center)
                if reach > 0.0 and best_other is not None:
                    dx = best_other[1][0]-center[0]
                    dy = best_other[1][1]-center[1]
                    norm = math.hypot(dx, dy)
                    point = (center[0]+reach*dx/norm,
                             center[1]+reach*dy/norm)
                    return self._action(
                        state, "clear", point, channel, "certified_clear",
                    )
            return self._action(
                state, "clear", center, channel, "certified_clear",
            )
        # A3 最优停止（B2 谱系，q3 同池中位 -33%）：M9 最近源区域半径收进
        # 猜清除阈值时先猜中心 clear；失败后 clear_guessed 置位转探测组。
        if self.use_optimal_stop:
            channel = self._nearest_remaining_channel(state, remaining)
            track = self._ensure_track_fields(state.sources[channel])
            if (track.region is not None
                    and track.region.get("status") == "bounded"
                    and not track.clear_guessed
                    and not track.certificate_failed):
                radius = track.region["minimum_enclosing_circle"]["radius"]
                if radius <= self.guess_clear_threshold_m:
                    center = tuple(
                        track.region["minimum_enclosing_circle"]["center"]
                    )
                    track.clear_guessed = True
                    return self._action(
                        state, "clear", center, channel, "guess_clear",
                    )
        # M9 近邻序（B2 批量定位谱系，中位 -9.4%）：兜底启用新定位任务的
        # 源按"当前点→区域中心"距离升序，替代频道号序，减少跨源巡航。
        nearest = self._nearest_remaining_channel(state, remaining)
        return self._single_source_action(state, state.sources[nearest])

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
            if track is not None:
                track = self._ensure_track_fields(track)
            if track is not None and track.region is not None:
                self._refresh_belief(state, track)
                if (response["measure_result"] == "direction"
                        and track.fallback_points):
                    if mode == "directional_probe":
                        self._rebuild_fallback_after_remeasure(state, track)
            if mode == "fallback_remeasure" and track is not None:
                # B2 分支 q3 无 fallback_remeasure 记账，在 q4 层补齐：
                track.fallback_remeasure_count += 1
                track.fallback_remeasure_points.append(tuple(action.position))
                if response["measure_result"] == "direction":
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
            elif (mode == "fallback_clear" and track is not None
                  and track.region is not None):
                # B2 分支 q3 无失败点记账，在 q4 层记录排除圆并刷新信念；
                # 连续多边形有意保持不变（不切割，保覆盖）。
                track = self._ensure_track_fields(track)
                point = tuple(action.position)
                track.failed_clear_points.append(point)
                track.failed_clear_disks.append((point, 20.0))
                self._refresh_belief(state, track)
