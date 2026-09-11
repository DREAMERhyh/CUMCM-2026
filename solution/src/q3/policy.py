"""Finite offline baseline state machine for omnidirectional sources."""

from dataclasses import dataclass, field

from common.domain import build_region_from_observations
from common.models import Action, BearingObservation
from q2.planner import Q2Config, plan_measurement
from .coverage import ring7, strip_clear_points


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
                 coverage_points=None):
        self.coverage_points = list(coverage_points or ring7())
        self.max_refinements = max_refinements
        self.error_deg = error_deg
        self.q2_config = Q2Config(error_deg=error_deg, circle_sides=16,
                                  scenario_limit=4,
                                  continuous_fim_enabled=False)

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
                if channel in state.cleared or channel in state.sources:
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
        radius = track.region["minimum_enclosing_circle"]["radius"]
        if radius <= 19.9 and not track.certificate_failed:
            center = tuple(track.region["minimum_enclosing_circle"]["center"])
            return self._action(state, "clear", center, track.channel,
                                "certified_clear")
        if track.refinements < self.max_refinements:
            point = self._refinement_point(state, track)
            return self._action(state, "measure", point, track.channel,
                                "refine")
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

    def _record_measurement(self, state, action, response):
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
        track.observations.append(observation)
        track.region = build_region_from_observations(
            track.observations, error_deg=self.error_deg, circle_sides=16)

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
            self._record_measurement(state, action, response)
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
            return
        if action.kind == "exit":
            state.exited = True

