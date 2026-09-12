"""Deterministic open-route planning over Q3 source service blocks.

The objects in this module are prediction summaries only.  They never mutate
``Q3State`` or ``SourceTrack`` and they do not replace the single-source
measure/clear decision made by :mod:`q3.policy`.
"""

from dataclasses import dataclass, field
import math
import time

from common.time_model import clear_cost, measure_cost

from .adaptive import nearest_neighbor_order


Point = tuple[float, float]
VALID_SERVICE_MODES = {
    "certified_clear", "measure_then_clear", "direct_clear",
}


@dataclass(frozen=True)
class SourceServiceSpec:
    """Current-state service prediction for one source channel."""

    channel: int
    mode: str
    entry_point: Point | None
    entry_action_kind: str
    entry_action_channel: int
    batch_channels: tuple[int, ...] = ()
    route_points: tuple[Point, ...] = ()
    source_version: tuple = ()
    reorder_clear_points: bool = True
    diagnostics: dict = field(default_factory=dict, compare=False)

    def __post_init__(self):
        if self.mode not in VALID_SERVICE_MODES:
            raise ValueError(f"未知服务模式：{self.mode}")
        if not 1 <= self.channel <= 20:
            raise ValueError("服务块频道必须在1至20之间。")
        if self.entry_action_kind not in ("measure", "clear"):
            raise ValueError("服务块首动作只能是measure或clear。")
        if not self.route_points:
            raise ValueError("服务块至少需要一个保守清除点。")


@dataclass(frozen=True)
class SourceServiceBlock:
    """One spec materialised from a predicted predecessor state."""

    channel: int
    mode: str
    entry_point: Point
    exit_point: Point
    entry_action_kind: str
    entry_action_channel: int
    batch_channels: tuple[int, ...]
    route_points: tuple[Point, ...]
    source_version: tuple
    transition_distance_m: float
    movement_distance_m: float
    local_cost_s: float
    total_cost_s: float
    exit_channel: int
    long_jump_count: int
    long_jump_distance_m: float
    diagnostics: dict = field(default_factory=dict, compare=False)


@dataclass(frozen=True)
class RouteEstimate:
    order: tuple[int, ...]
    blocks: tuple[SourceServiceBlock, ...]
    total_virtual_time_s: float
    total_movement_distance_m: float
    long_jump_count: int
    long_jump_distance_m: float
    end_position: Point
    end_channel: int


@dataclass(frozen=True)
class RoutePlan:
    status: str
    reason: str
    estimate: RouteEstimate | None
    insertion_order: tuple[int, ...]
    two_opt_iterations: int
    cpu_wall_time_s: float


class RoutePlanningTimeout(RuntimeError):
    """Raised before a complete insertion route can be produced."""


def _movement_segments(points, start):
    current = tuple(start)
    result = []
    for point in points:
        point = tuple(point)
        result.append(math.dist(current, point))
        current = point
    return result


def _long_jump_summary(distances, threshold_m=1000.0):
    long = [distance for distance in distances
            if distance >= threshold_m - 1e-9]
    return len(long), sum(long)


def materialize_service_block(spec, incoming_position, incoming_channel):
    """Materialise one conservative block from a predicted predecessor."""
    incoming_position = tuple(incoming_position)
    clear_points = list(spec.route_points)
    if spec.reorder_clear_points:
        clear_points = nearest_neighbor_order(clear_points, (
            spec.entry_point
            if spec.mode == "measure_then_clear"
            else incoming_position
        ))
    if not clear_points:
        raise ValueError("物化服务块时清除点不能为空。")

    total_s = 0.0
    current_position = incoming_position
    current_channel = incoming_channel
    movement_distances = []

    if spec.mode == "measure_then_clear":
        entry = tuple(spec.entry_point)
        timing = measure_cost(
            current_position, entry, current_channel,
            spec.entry_action_channel,
        )
        movement_distances.append(math.dist(current_position, entry))
        total_s += timing.total_s
        current_position = entry
        current_channel = spec.entry_action_channel
        for channel in spec.batch_channels:
            if channel == spec.entry_action_channel:
                continue
            timing = measure_cost(
                current_position, current_position, current_channel, channel
            )
            total_s += timing.total_s
            current_channel = channel
    else:
        entry = tuple(clear_points[0])

    for index, point in enumerate(clear_points):
        point = tuple(point)
        movement_distances.append(math.dist(current_position, point))
        timing = clear_cost(
            current_position, point, index == len(clear_points) - 1
        )
        total_s += timing.total_s
        current_position = point

    transition_distance = math.dist(incoming_position, entry)
    movement_distance = sum(movement_distances)
    long_count, long_distance = _long_jump_summary(movement_distances)
    local_cost = total_s - transition_distance / 5.0
    return SourceServiceBlock(
        channel=spec.channel,
        mode=spec.mode,
        entry_point=entry,
        exit_point=current_position,
        entry_action_kind=spec.entry_action_kind,
        entry_action_channel=spec.entry_action_channel,
        batch_channels=spec.batch_channels,
        route_points=tuple(clear_points),
        source_version=spec.source_version,
        transition_distance_m=transition_distance,
        movement_distance_m=movement_distance,
        local_cost_s=local_cost,
        total_cost_s=total_s,
        exit_channel=current_channel,
        long_jump_count=long_count,
        long_jump_distance_m=long_distance,
        diagnostics=dict(spec.diagnostics),
    )


def evaluate_open_service_route(order, specs, start_position, start_channel):
    """Fully re-materialise and score one open source order."""
    order = tuple(order)
    if len(order) != len(set(order)):
        raise ValueError("开放路线不能重复包含同一频道。")
    missing = [channel for channel in order if channel not in specs]
    if missing:
        raise ValueError(f"开放路线缺少服务规格：{missing}")
    position = tuple(start_position)
    channel = start_channel
    blocks = []
    for source_channel in order:
        block = materialize_service_block(
            specs[source_channel], position, channel
        )
        blocks.append(block)
        position = block.exit_point
        channel = block.exit_channel
    return RouteEstimate(
        order=order,
        blocks=tuple(blocks),
        total_virtual_time_s=sum(block.total_cost_s for block in blocks),
        total_movement_distance_m=sum(
            block.movement_distance_m for block in blocks
        ),
        long_jump_count=sum(block.long_jump_count for block in blocks),
        long_jump_distance_m=sum(
            block.long_jump_distance_m for block in blocks
        ),
        end_position=position,
        end_channel=channel,
    )


def _estimate_key(estimate):
    return (
        estimate.total_virtual_time_s,
        estimate.total_movement_distance_m,
        estimate.long_jump_count,
        estimate.order,
    )


def cheapest_insertion(specs, start_position, start_channel, *, deadline=None):
    """Construct a complete deterministic open route by cheapest insertion."""
    if not specs:
        return evaluate_open_service_route(
            (), specs, start_position, start_channel
        )
    remaining = set(specs)
    first_candidates = []
    for channel in sorted(remaining):
        if deadline is not None and time.perf_counter() >= deadline:
            raise RoutePlanningTimeout("insertion_before_first_complete_route")
        estimate = evaluate_open_service_route(
            (channel,), specs, start_position, start_channel
        )
        first_candidates.append((_estimate_key(estimate), channel, estimate))
    _, first, current = min(first_candidates)
    order = [first]
    remaining.remove(first)

    while remaining:
        candidates = []
        for channel in sorted(remaining):
            for position in range(len(order) + 1):
                if deadline is not None and time.perf_counter() >= deadline:
                    raise RoutePlanningTimeout(
                        "insertion_before_complete_route"
                    )
                candidate_order = [*order]
                candidate_order.insert(position, channel)
                estimate = evaluate_open_service_route(
                    candidate_order, specs, start_position, start_channel
                )
                delta = (
                    estimate.total_virtual_time_s
                    - current.total_virtual_time_s
                )
                candidates.append((
                    delta,
                    estimate.total_movement_distance_m,
                    estimate.long_jump_count,
                    channel,
                    position,
                    estimate.order,
                    estimate,
                ))
        selected = min(candidates)
        selected_channel = selected[3]
        current = selected[-1]
        order = list(current.order)
        remaining.remove(selected_channel)
    return current


def improve_two_opt(initial, specs, start_position, start_channel, *,
                    max_iterations=20, deadline=None, tolerance=1e-9):
    """Apply deterministic best-improvement 2-opt with full rescoring."""
    if max_iterations < 0:
        raise ValueError("2-opt迭代上限不能为负。")
    current = initial
    iterations = 0
    timed_out = False
    while iterations < max_iterations and len(current.order) >= 2:
        best = current
        for first in range(len(current.order) - 1):
            for last in range(first + 1, len(current.order)):
                if deadline is not None and time.perf_counter() >= deadline:
                    timed_out = True
                    return current, iterations, timed_out
                candidate_order = (
                    current.order[:first]
                    + tuple(reversed(current.order[first:last + 1]))
                    + current.order[last + 1:]
                )
                candidate = evaluate_open_service_route(
                    candidate_order, specs, start_position, start_channel
                )
                if _estimate_key(candidate) < _estimate_key(best):
                    best = candidate
        if (best.total_virtual_time_s
                >= current.total_virtual_time_s - tolerance):
            break
        current = best
        iterations += 1
    return current, iterations, timed_out


def plan_service_route(specs, start_position, start_channel, *,
                       cpu_time_limit_s=0.25, max_2opt_iterations=20):
    """Return insertion + 2-opt result or a finite fallback status."""
    if cpu_time_limit_s <= 0.0:
        raise ValueError("路线规划CPU软截止必须为正数。")
    started = time.perf_counter()
    deadline = started + cpu_time_limit_s
    try:
        insertion = cheapest_insertion(
            specs, start_position, start_channel, deadline=deadline
        )
    except (RoutePlanningTimeout, RuntimeError, ValueError) as error:
        return RoutePlan(
            status="fallback",
            reason=f"{type(error).__name__}:{error}",
            estimate=None,
            insertion_order=(),
            two_opt_iterations=0,
            cpu_wall_time_s=time.perf_counter() - started,
        )
    improved, iterations, timed_out = improve_two_opt(
        insertion, specs, start_position, start_channel,
        max_iterations=max_2opt_iterations, deadline=deadline,
    )
    return RoutePlan(
        status="partial" if timed_out else "ok",
        reason="two_opt_time_limit" if timed_out else "complete",
        estimate=improved,
        insertion_order=insertion.order,
        two_opt_iterations=iterations,
        cpu_wall_time_s=time.perf_counter() - started,
    )
