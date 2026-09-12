"""Parse Q3 JSONL logs into deterministic action-by-action display frames."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import math
from pathlib import Path

from common.domain import build_region_from_observations
from common.models import BearingObservation, TimeBreakdown
from common.time_model import clear_cost, measure_cost

Point = tuple[float, float]


@dataclass(frozen=True)
class Frame:
    """State immediately after one logged action; frame zero is pre-entry."""

    index: int
    sequence: int | None
    action: dict | None
    response: dict | None
    robot_position: Point
    current_channel: int
    virtual_time_s: float
    action_virtual_delta_s: float
    regions: dict[int, tuple[Point, ...]]
    active_sources: dict[int, Point]
    cleared_sources: dict[int, Point]
    successful_clear_positions: tuple[Point, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class TimeSummary:
    total_virtual_s: float
    real_wall_s: float
    movement_s: float
    switching_s: float
    measurement_s: float
    optical_s: float
    laser_s: float
    unaccounted_s: float

    def items(self):
        return (
            ("移动", self.movement_s),
            ("换频", self.switching_s),
            ("测量", self.measurement_s),
            ("光学", self.optical_s),
            ("激光", self.laser_s),
        )

    def percentage(self, seconds):
        if self.total_virtual_s <= 0:
            return 0.0
        return 100.0 * seconds / self.total_virtual_s


@dataclass(frozen=True)
class Replay:
    path: Path
    records: tuple[dict, ...]
    frames: tuple[Frame, ...]
    time_summary: TimeSummary
    action_counts: dict[str, int]
    clear_successes: int
    clear_failures: int


def _point(value, *, field):
    if not isinstance(value, dict) or not {"x", "y"} <= set(value):
        raise ValueError(f"{field} 必须包含 x、y。")
    point = float(value["x"]), float(value["y"])
    if not all(math.isfinite(item) for item in point):
        raise ValueError(f"{field} 坐标必须为有限数。")
    return point


def read_jsonl(path):
    """Read a complete JSONL file with line-numbered validation errors."""
    records = []
    with Path(path).open("r", encoding="utf-8-sig") as stream:
        for line_number, raw in enumerate(stream, 1):
            if not raw.strip():
                continue
            try:
                record = json.loads(raw)
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"第 {line_number} 行不是合法 JSON：{error.msg}"
                ) from error
            if not isinstance(record, dict):
                raise ValueError(f"第 {line_number} 行必须是 JSON 对象。")
            records.append(record)
    if not records:
        raise ValueError("日志中没有动作记录。")
    return records


def resolve_log_path(value=None, *, log_dir=None):
    """Resolve an explicit log or choose the newest q3_*.jsonl."""
    directory = Path(log_dir or "output/sim").resolve()
    if value is not None:
        candidate = Path(value)
        if candidate.is_file():
            return candidate.resolve()
        if not candidate.is_absolute():
            nested = directory / candidate
            if nested.is_file():
                return nested.resolve()
        raise FileNotFoundError(f"找不到日志：{value}")
    candidates = list(directory.glob("q3_*.jsonl"))
    if not candidates:
        raise FileNotFoundError(f"{directory} 中没有 q3_*.jsonl。")
    return max(candidates, key=lambda item: (item.stat().st_mtime_ns, item.name))


def _region_center(region):
    if region is None or region.get("status") != "bounded":
        return None
    circle = region.get("minimum_enclosing_circle")
    if not circle:
        return None
    return tuple(circle["center"])


def _add_breakdown(total, part):
    return TimeBreakdown(
        movement_s=total.movement_s + part.movement_s,
        switching_s=total.switching_s + part.switching_s,
        measurement_s=total.measurement_s + part.measurement_s,
        optical_s=total.optical_s + part.optical_s,
        laser_s=total.laser_s + part.laser_s,
    )


def _snapshot(index, sequence, action, response, position, current_channel,
              virtual_time, delta, regions, near_points, cleared, clear_path,
              warnings):
    polygons = {
        channel: tuple(tuple(point) for point in region["vertices"])
        for channel, region in regions.items()
        if region.get("status") == "bounded"
        and len(region.get("vertices", [])) >= 3
    }
    estimates = {}
    for channel, region in regions.items():
        center = _region_center(region)
        if center is not None:
            estimates[channel] = center
    for channel, point in near_points.items():
        estimates.setdefault(channel, point)
    active = {
        channel: point for channel, point in estimates.items()
        if channel not in cleared
    }
    return Frame(
        index=index,
        sequence=sequence,
        action=action,
        response=response,
        robot_position=position,
        current_channel=current_channel,
        virtual_time_s=virtual_time,
        action_virtual_delta_s=delta,
        regions=polygons,
        active_sources=active,
        cleared_sources=dict(cleared),
        successful_clear_positions=tuple(clear_path),
        warnings=tuple(warnings),
    )


def build_replay(path, records, *, error_deg=1.005, circle_sides=16):
    """Replay accepted actions and reconstruct posterior source regions."""
    position = (0.0, 0.0)
    current_channel = 1
    virtual_time = 0.0
    observations = {}
    regions = {}
    near_points = {}
    cleared = {}
    clear_path = []
    warnings = []
    breakdown = TimeBreakdown()
    counts = {"enter": 0, "measure": 0, "clear": 0, "exit": 0}
    clear_successes = 0
    clear_failures = 0

    frames = [
        _snapshot(
            0, None, None, None, position, current_channel, virtual_time, 0.0,
            regions, near_points, cleared, clear_path, warnings,
        )
    ]

    for index, record in enumerate(records, 1):
        action = record.get("action")
        if not isinstance(action, dict):
            raise ValueError(f"第 {index} 条记录缺少 action 对象。")
        kind = action.get("kind")
        if kind not in counts:
            raise ValueError(f"第 {index} 条记录动作类型无效：{kind!r}。")
        counts[kind] += 1
        response = record.get("response")
        accepted = isinstance(response, dict) and response.get("accepted") is True
        previous_virtual = virtual_time

        if accepted and "virtual_time_s" in response:
            virtual_time = float(response["virtual_time_s"])
        delta = virtual_time - previous_virtual
        if delta < -1e-7:
            warnings.append(f"动作 {index} 的虚拟时间发生倒退。")

        if accepted and kind in ("measure", "clear"):
            target = _point(action.get("position"), field=f"动作 {index} position")
            channel = int(action["channel"])
            if kind == "measure":
                cost = measure_cost(position, target, current_channel, channel)
                breakdown = _add_breakdown(breakdown, cost)
                position = target
                current_channel = channel
                result = response.get("measure_result")
                if result == "direction":
                    bearing = float(response["svd_deg"])
                    history = observations.setdefault(channel, [])
                    history.append(BearingObservation(
                        target, channel, "direction", bearing
                    ))
                    try:
                        region = build_region_from_observations(
                            history,
                            error_deg=error_deg,
                            circle_sides=circle_sides,
                        )
                    except ValueError as error:
                        warnings.append(f"频道 {channel} 定位区域失败：{error}")
                        regions.pop(channel, None)
                    else:
                        if region.get("status") == "bounded":
                            regions[channel] = region
                        else:
                            warnings.append(
                                f"频道 {channel} 定位区域为 {region.get('status')}。"
                            )
                            regions.pop(channel, None)
                elif result == "near":
                    near_points[channel] = target
            else:
                success = response.get("clear_result") == "success"
                cost = clear_cost(position, target, success)
                breakdown = _add_breakdown(breakdown, cost)
                position = target
                if success:
                    clear_successes += 1
                    estimate = _region_center(regions.get(channel))
                    cleared[channel] = estimate or near_points.get(channel) or target
                    clear_path.append(target)
                    near_points.pop(channel, None)
                elif response.get("clear_result") == "no_target_in_range":
                    clear_failures += 1

        sequence = record.get("sequence", index)
        frames.append(_snapshot(
            index, sequence, action, response, position, current_channel,
            virtual_time, delta, regions, near_points, cleared, clear_path,
            warnings,
        ))

    first_stamp = records[0].get("recorded_at_utc")
    last_stamp = records[-1].get("recorded_at_utc")
    real_wall_s = 0.0
    if first_stamp and last_stamp:
        try:
            real_wall_s = (
                datetime.fromisoformat(last_stamp)
                - datetime.fromisoformat(first_stamp)
            ).total_seconds()
        except ValueError:
            warnings.append("recorded_at_utc 无法解析，现实时间未统计。")

    unaccounted = virtual_time - breakdown.total_s
    tolerance = max(1e-5, abs(virtual_time) * 1e-8)
    if abs(unaccounted) > tolerance:
        warnings.append(f"虚拟时间与本地价格表相差 {unaccounted:.6f} s。")
        last = frames[-1]
        frames[-1] = Frame(
            index=last.index,
            sequence=last.sequence,
            action=last.action,
            response=last.response,
            robot_position=last.robot_position,
            current_channel=last.current_channel,
            virtual_time_s=last.virtual_time_s,
            action_virtual_delta_s=last.action_virtual_delta_s,
            regions=last.regions,
            active_sources=last.active_sources,
            cleared_sources=last.cleared_sources,
            successful_clear_positions=last.successful_clear_positions,
            warnings=tuple(warnings),
        )
    summary = TimeSummary(
        total_virtual_s=virtual_time,
        real_wall_s=real_wall_s,
        movement_s=breakdown.movement_s,
        switching_s=breakdown.switching_s,
        measurement_s=breakdown.measurement_s,
        optical_s=breakdown.optical_s,
        laser_s=breakdown.laser_s,
        unaccounted_s=unaccounted,
    )
    return Replay(
        path=Path(path).resolve(),
        records=tuple(records),
        frames=tuple(frames),
        time_summary=summary,
        action_counts=counts,
        clear_successes=clear_successes,
        clear_failures=clear_failures,
    )


def load_replay(path, *, error_deg=1.005, circle_sides=16):
    path = Path(path).resolve()
    return build_replay(
        path,
        read_jsonl(path),
        error_deg=error_deg,
        circle_sides=circle_sides,
    )
