"""Finite offline baseline state machine for omnidirectional sources."""

from dataclasses import dataclass, field

from common.domain import build_region_from_observations
from common.models import Action, BearingObservation
from q2.planner import Q2Config, plan_measurement
from .coverage import SCAN_LAYOUTS, ring7, strip_clear_points


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
    exclusion_circles: list[tuple[tuple[float, float], float]] = field(
        default_factory=list)
    clear_guessed: bool = False


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
    phase: str = "scan"
    sources: dict[int, SourceTrack] = field(default_factory=dict)
    cleared: set[int] = field(default_factory=set)
    absent: set[int] = field(default_factory=set)
    forced_clear: tuple[tuple[float, float], int] | None = None
    pending: Action | None = None
    pending_mode: str | None = None
    sequence: int = 0


class Q3Policy:
    def __init__(self, *, max_refinements=2, error_deg=1.005,
                 coverage_points=None, fim_cpu_time_limit_s=6.0,
                 scan_layout="pure_ring8", use_no_signal_pruning=False,
                 continuous_objective="fim", use_optimal_stop=True,
                 stop_cost_per_metre=0.5, guess_clear_threshold_m=40.0,
                 interleaved_scan_refine=True):
        if fim_cpu_time_limit_s <= 0:
            raise ValueError("FIM真实计算时限必须为正数。")
        if scan_layout not in SCAN_LAYOUTS:
            raise ValueError(
                f"未知扫描布局：{scan_layout}；可选 {sorted(SCAN_LAYOUTS)}。"
            )
        if continuous_objective not in ("fim", "diameter"):
            raise ValueError("continuous_objective 必须为 fim 或 diameter。")
        if stop_cost_per_metre <= 0 or guess_clear_threshold_m <= 0:
            raise ValueError("停止阈值与折算系数必须为正数。")
        self.scan_layout = scan_layout
        self.use_no_signal_pruning = use_no_signal_pruning
        self.continuous_objective = continuous_objective
        self.use_optimal_stop = use_optimal_stop
        self.stop_cost_per_metre = stop_cost_per_metre
        self.guess_clear_threshold_m = guess_clear_threshold_m
        self.interleaved_scan_refine = interleaved_scan_refine
        self.coverage_points = list(coverage_points or SCAN_LAYOUTS[scan_layout]())
        self.max_refinements = max_refinements
        self.error_deg = error_deg
        self.q2_config = Q2Config(error_deg=error_deg, circle_sides=16,
                                  scenario_limit=4,
                                  continuous_fim_enabled=True,
                                  fim_cpu_time_limit_s=fim_cpu_time_limit_s,
                                  continuous_objective=continuous_objective,
                                  near_optimal_region_mode="off")

    def initial_state(self):
        return Q3State()

    def _action(self, state, kind, position=None, channel=None, mode=None):
        state.sequence += 1
        state.pending = Action(kind, f"{kind}-{state.sequence}", position, channel)
        state.pending_mode = mode
        return state.pending

    def _scan_action(self, state):
        while state.scan_point_index < len(self.coverage_points):
            if not state.scan_order:
                state.scan_order = [state.current_channel] + [
                    channel for channel in range(1, 21)
                    if channel != state.current_channel
                ]
                state.scan_channel_index = 0
            while state.scan_channel_index < len(state.scan_order):
                channel = state.scan_order[state.scan_channel_index]
                if channel in state.cleared:
                    state.scan_channel_index += 1
                    continue
                if (channel in state.sources
                        and not self.interleaved_scan_refine):
                    state.scan_channel_index += 1
                    continue
                return self._action(state, "measure",
                                    self.coverage_points[state.scan_point_index],
                                    channel, "scan")
            state.scan_point_index += 1
            state.scan_order = []
        state.absent = set(range(1, 21))-set(state.sources)-state.cleared
        state.phase = "resolve"
        return None

    def _refinement_point(self, state, track):
        plan = plan_measurement(
            track.region, track.observations,
            current_position=state.position,
            current_channel=state.current_channel,
            target_channel=track.channel,
            config=self.q2_config,
        )
        return tuple(plan["selected_point"])

    def _resolve_action(self, state):
        remaining = [channel for channel in sorted(state.sources)
                     if channel not in state.cleared]
        if not remaining:
            if state.cleared | state.absent != set(range(1, 21)):
                raise RuntimeError("频道终止证书不完整。")
            state.phase = "exit"
            return None
        track = state.sources[remaining[0]]
        if (track.region is None
                or track.region.get("status") != "bounded"):
            # 参数越界防御（E3 实证）：error_deg 低于真实误差界时窄锥交会
            # 可能产生无界后验区域（minimum_enclosing_circle 为 None），
            # 无法细化解；此时直接走 fallback 保底，不崩溃。
            return self._fallback_action(state, track)
        radius = track.region["minimum_enclosing_circle"]["radius"]
        if radius <= 19.9 and not track.certificate_failed:
            center = tuple(track.region["minimum_enclosing_circle"]["center"])
            return self._action(state, "clear", center, track.channel,
                                "certified_clear")
        # A3 最优停止（默认关闭）：区域直径已收缩到清除保证半径（阈值
        # 默认 40m = 20m 清除半径 x2）时，直接猜中心点 clear 的最坏虚拟
        # 成本（miss 后仍可走既有 refine/fallback）只比直接 refine 多 3s/
        # 源，却省下一次规划的全部墙钟（每源 6s+），对 20 分钟现实窗口
        # 尤其有利。最坏情形口径：不假设命中概率，只比较成本下界。
        # 失败后 clear_guessed=True，不再重复猜测，转入正常 refine。
        if (self.use_optimal_stop and not track.clear_guessed
                and not track.certificate_failed
                and radius <= self.guess_clear_threshold_m):
            center = tuple(track.region["minimum_enclosing_circle"]["center"])
            track.clear_guessed = True
            return self._action(state, "clear", center, track.channel,
                                "guess_clear")
        if track.refinements < self.max_refinements:
            point = self._refinement_point(state, track)
            return self._action(state, "measure", point, track.channel,
                                "refine")
        return self._fallback_action(state, track)

    def _fallback_action(self, state, track):
        """有限清除保底：条带网格逐点清除（证书与细化均失败的兜底）。"""
        if not track.fallback_points:
            first = track.observations[0]
            track.fallback_points = list(strip_clear_points(first.position,
                                                            first.bearing_deg))
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

    def _record_measurement(self, state, action, response, mode=None):
        result = response["measure_result"]
        if result == "near":
            state.forced_clear = (action.position, action.channel)
            return
        if result == "no_signal":
            # A1 排除圆修剪（默认关闭）：仅对"已被 direction/near 确认有源
            # 的频道"的细化测量 no_signal 追加排除圆 B(测点, 1000)——
            # 有效接收半径下界 1000 保证真实源不在此圆内（全向源前提）；
            # 扫描期 no_signal 只用于 absent 判定，不建排除圆。
            if (mode == "refine" and self.use_no_signal_pruning
                    and action.channel in state.sources):
                track = state.sources[action.channel]
                track.exclusion_circles.append(
                    (tuple(action.position), 1000.0))
                if track.region is not None:
                    track.region["exclusion_circles"] = list(
                        track.exclusion_circles)
            return
        observation = BearingObservation(action.position, action.channel,
                                         "direction", response["svd_deg"])
        track = state.sources.setdefault(action.channel,
                                         SourceTrack(action.channel))
        track.observations.append(observation)
        track.region = build_region_from_observations(
            track.observations, error_deg=self.error_deg, circle_sides=16)
        track.region["exclusion_circles"] = list(track.exclusion_circles)

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
            self._record_measurement(state, action, response, mode)
            if mode == "scan":
                state.scan_channel_index += 1
            elif mode == "refine":
                state.sources[action.channel].refinements += 1
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
                track.fallback_index += 1
            elif mode == "guess_clear":
                pass  # clear_guessed 已置位，下一轮转入既有 refine 流程
            return
        if action.kind == "exit":
            state.exited = True

