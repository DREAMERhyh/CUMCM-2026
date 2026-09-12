"""Finite mixed-source belief used only to rank certified Q4 actions.

The continuous safety certificate remains the conservative position polygon
and the geometric probe/clear covers.  This module deliberately keeps the
joint source type, position, receive radius and emission direction as a finite
decision approximation; it is not a probability or continuous-coverage proof.
"""

from dataclasses import dataclass
import math

from common.domain import representative_points
from q1.geometry import contains

from .directional import is_visible


@dataclass(frozen=True)
class Q4Measurement:
    position: tuple[float, float]
    result: str
    bearing_deg: float | None = None


@dataclass(frozen=True)
class JointScenario:
    position: tuple[float, float]
    receive_radius: float
    direction_deg: float | None
    weight: float

    @property
    def source_kind(self):
        return "omni" if self.direction_deg is None else "directional"


@dataclass(frozen=True)
class JointBelief:
    scenarios: tuple[JointScenario, ...]
    history_count: int
    position_sample_count: int
    status: str = "ok"

    def visible_weight(self, point):
        return sum(
            item.weight
            for item in self.scenarios
            if is_visible(
                item.position, item.direction_deg, point,
                item.receive_radius,
            )
        )

    def outcome_weights(self, point):
        visible = self.visible_weight(point)
        near = sum(
            item.weight
            for item in self.scenarios
            if (math.dist(item.position, point) <= 5.0+1e-9
                and is_visible(
                    item.position, item.direction_deg, point,
                    item.receive_radius,
                ))
        )
        return {
            "near": near,
            "direction": max(0.0, visible-near),
            "no_signal": max(0.0, 1.0-visible),
        }

    def summary(self):
        omni = sum(
            item.weight for item in self.scenarios
            if item.direction_deg is None
        )
        directions = sorted({
            round(item.direction_deg, 6)
            for item in self.scenarios
            if item.direction_deg is not None
        })
        radii = sorted({item.receive_radius for item in self.scenarios})
        return {
            "status": self.status,
            "scenario_count": len(self.scenarios),
            "position_sample_count": self.position_sample_count,
            "history_count": self.history_count,
            "omni_weight": omni,
            "directional_weight": max(0.0, 1.0-omni),
            "receive_radius_support_m": radii,
            "direction_support_deg": directions,
        }


def _angle_difference(first, second):
    return abs((first-second+180.0) % 360.0-180.0)


def _unique_points(points):
    seen, result = set(), []
    for point in points:
        point = tuple(float(value) for value in point)
        key = round(point[0], 8), round(point[1], 8)
        if key in seen:
            continue
        seen.add(key)
        result.append(point)
    return result


def _position_samples(region, *, limit, arena_radius):
    vertices = [tuple(point) for point in region.get("vertices", ())]
    if not vertices:
        return []
    candidates = representative_points(vertices, limit=max(limit*2, 12))
    candidates.append(tuple(region["minimum_enclosing_circle"]["center"]))

    xs = [point[0] for point in vertices]
    ys = [point[1] for point in vertices]
    grid_side = max(3, math.ceil(math.sqrt(limit)))
    for iy in range(grid_side):
        y = min(ys)+(max(ys)-min(ys))*iy/max(1, grid_side-1)
        for ix in range(grid_side):
            x = min(xs)+(max(xs)-min(xs))*ix/max(1, grid_side-1)
            candidates.append((x, y))

    valid = [
        point for point in _unique_points(candidates)
        if (math.hypot(*point) <= arena_radius+1e-7
            and contains(region["planes"], point))
    ]
    center = tuple(region["minimum_enclosing_circle"]["center"])
    valid.sort(key=lambda point: (math.dist(point, center), point))
    if len(valid) <= limit:
        return valid
    if limit == 1:
        return [valid[0]]
    indices = [round(i*(len(valid)-1)/(limit-1)) for i in range(limit)]
    return [valid[index] for index in indices]


def _direction_samples(position, history, step_deg):
    values = {float(value) for value in range(0, 360, step_deg)}
    for measurement in history:
        dx = measurement.position[0]-position[0]
        dy = measurement.position[1]-position[1]
        if math.hypot(dx, dy) <= 1e-12:
            continue
        towards_sensor = math.degrees(math.atan2(dy, dx)) % 360.0
        for offset in (0.0, -90.0, 90.0, -89.999, 89.999,
                       -90.001, 90.001):
            values.add((towards_sensor+offset) % 360.0)
    return sorted(values)


def scenario_matches_history(scenario, history, *, error_deg=1.005):
    for measurement in history:
        visible = is_visible(
            scenario.position, scenario.direction_deg,
            measurement.position, scenario.receive_radius,
        )
        distance = math.dist(scenario.position, measurement.position)
        if measurement.result == "no_signal":
            if visible:
                return False
        elif measurement.result == "near":
            if not visible or distance > 5.0+1e-9:
                return False
        elif measurement.result == "direction":
            if not visible or distance <= 5.0+1e-9:
                return False
            true_bearing = math.degrees(math.atan2(
                scenario.position[1]-measurement.position[1],
                scenario.position[0]-measurement.position[0],
            )) % 360.0
            if _angle_difference(true_bearing, measurement.bearing_deg) \
                    > error_deg+1e-7:
                return False
        else:
            raise ValueError(f"未知Q4检测结果：{measurement.result}")
    return True


def build_joint_belief(
        region, history, *, error_deg=1.005, arena_radius=1800.0,
        position_limit=12, direction_step_deg=10,
        receive_radii=(1000.0, 1250.0, 1500.0),
        omni_prior_weight=0.5, excluded_disks=()):
    """Rebuild a finite joint belief from all signal and no-signal records."""
    if region is None or region.get("status") != "bounded":
        return JointBelief((), len(history), 0, "unbounded_position")
    if position_limit < 1:
        raise ValueError("位置场景上限至少为1。")
    if direction_step_deg < 1 or 360 % direction_step_deg != 0:
        raise ValueError("方向采样步长必须是360的正整数因子。")
    if not 0.0 <= omni_prior_weight <= 1.0:
        raise ValueError("全向源先验权重必须位于[0,1]。")
    radii = tuple(float(value) for value in receive_radii)
    if not radii or any(value < 1000.0 or value > 1500.0
                        for value in radii):
        raise ValueError("接收半径场景必须位于[1000,1500]米。")
    excluded_disks = tuple(
        (tuple(center), float(radius)) for center, radius in excluded_disks
    )
    if any(radius < 0.0 for _, radius in excluded_disks):
        raise ValueError("清除失败排除圆半径不能为负数。")

    history = tuple(history)
    positions = _position_samples(
        region, limit=position_limit, arena_radius=arena_radius,
    )
    weighted = []
    position_radius_count = max(1, len(positions)*len(radii))
    for position in positions:
        if any(math.dist(position, center) <= radius+1e-9
               for center, radius in excluded_disks):
            continue
        omni_base = omni_prior_weight/position_radius_count
        directions = _direction_samples(
            position, history, direction_step_deg,
        )
        directional_base = (
            (1.0-omni_prior_weight)
            / max(1, position_radius_count*len(directions))
        )
        for radius in radii:
            omni = JointScenario(position, radius, None, omni_base)
            if scenario_matches_history(omni, history,
                                        error_deg=error_deg):
                weighted.append(omni)
            for direction in directions:
                scenario = JointScenario(
                    position, radius, direction, directional_base,
                )
                if scenario_matches_history(
                        scenario, history, error_deg=error_deg):
                    weighted.append(scenario)

    total = sum(item.weight for item in weighted)
    if total <= 0.0:
        return JointBelief((), len(history), len(positions),
                           "empty_finite_support")
    normalized = tuple(
        JointScenario(
            item.position, item.receive_radius, item.direction_deg,
            item.weight/total,
        )
        for item in weighted
    )
    return JointBelief(normalized, len(history), len(positions))
