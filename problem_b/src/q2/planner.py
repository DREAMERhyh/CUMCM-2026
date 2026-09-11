"""Auditable set-based second-measurement planner for B-Q2."""

from dataclasses import asdict, dataclass
import math

from q1.geometry import bearing_planes, intersect_halfplanes

from common.domain import (build_region_from_observations, circle_outer_planes,
                           max_vertex_distance, representative_points)
from common.models import BearingObservation
from common.time_model import measure_cost
from .candidates import build_candidate_regions, generate_candidates


@dataclass(frozen=True)
class Q2Config:
    error_deg: float = 1.005
    arena_radius: float = 1800.0
    min_receive_radius: float = 1000.0
    max_receive_radius: float = 1500.0
    circle_sides: int = 24
    candidate_region_sides: int = 72
    scenario_limit: int = 8
    uncertainty_seconds_per_metre: float = 0.5


def _posterior_radius(region, sensor, target, error, config):
    distance = math.dist(sensor, target)
    if distance <= 5.0:
        return min(5.0, region["minimum_enclosing_circle"]["radius"])
    true_bearing = math.degrees(math.atan2(target[1]-sensor[1],
                                           target[0]-sensor[0])) % 360
    planes = list(region["planes"])
    planes.extend(circle_outer_planes(sensor, config.max_receive_radius,
                                      config.circle_sides))
    planes.extend(bearing_planes(sensor, true_bearing+error,
                                 config.error_deg))
    posterior = intersect_halfplanes(planes)
    if posterior["status"] != "bounded":
        return float("inf")
    return posterior["minimum_enclosing_circle"]["radius"]


def _fim_proxy(sensor, current_position, nominal_target, action_seconds):
    a = (nominal_target[0]-current_position[0],
         nominal_target[1]-current_position[1])
    b = (nominal_target[0]-sensor[0], nominal_target[1]-sensor[1])
    da, db = math.hypot(*a), math.hypot(*b)
    if da <= 5 or db <= 5:
        return 0.0
    sine = abs(a[0]*b[1]-a[1]*b[0])/(da*db)
    return sine/(da*db*action_seconds)


def score_candidates(region, observations, candidates, current_position,
                     current_channel, target_channel, config=Q2Config()):
    vertices = region["vertices"]
    scenarios = representative_points(vertices, config.scenario_limit)
    current_radius = region["minimum_enclosing_circle"]["radius"]
    nominal = tuple(region["minimum_enclosing_circle"]["center"])
    scores = []
    for sensor in candidates:
        timing = measure_cost(current_position, sensor, current_channel,
                              target_channel)
        guaranteed = max_vertex_distance(sensor, vertices) <= config.min_receive_radius + 1e-7
        radii = []
        for target in scenarios:
            distance = math.dist(sensor, target)
            if distance > config.max_receive_radius:
                radii.append(current_radius)
                continue
            for error in (-config.error_deg, 0.0, config.error_deg):
                radii.append(_posterior_radius(region, sensor, target, error,
                                               config))
            if distance > config.min_receive_radius:
                radii.append(current_radius)  # unknown R may produce no_signal
        if not guaranteed:
            radii.append(current_radius)
        worst_radius = max(radii, default=current_radius)
        score = timing.total_s + config.uncertainty_seconds_per_metre*worst_radius
        scores.append({
            "point": tuple(sensor),
            "guaranteed_reception": guaranteed,
            "worst_case_radius_m": worst_radius,
            "action_time_s": timing.total_s,
            "time_breakdown": timing.as_dict(),
            "score": score,
            "fim_proxy_per_s": _fim_proxy(sensor, observations[0].position,
                                             nominal, timing.total_s),
        })
    return scores


def plan_measurement(region, observations, *, current_position=None,
                     current_channel=None, target_channel=None,
                     config=Q2Config()):
    observations = list(observations)
    directions = [obs for obs in observations if obs.result == "direction"]
    if not directions:
        raise ValueError("测点规划至少需要一次 direction 观测。")
    first = directions[0]
    current_position = tuple(current_position or observations[-1].position)
    target_channel = target_channel or first.channel
    current_channel = current_channel or target_channel
    candidate_regions = build_candidate_regions(
        region,
        min_receive_radius=config.min_receive_radius,
        max_receive_radius=config.max_receive_radius,
        circle_sides=config.candidate_region_sides,
    )
    candidates = generate_candidates(
        region, current_position, first.bearing_deg,
        guaranteed_region=candidate_regions["guaranteed_reception"],
    )
    scores = score_candidates(region, observations, candidates,
                              current_position, current_channel,
                              target_channel, config)
    scores = sorted(scores, key=lambda item: (item["score"],
                                               -item["fim_proxy_per_s"],
                                               item["point"]))
    for index, item in enumerate(scores, 1):
        item["candidate_id"] = f"C{index:02d}"
    guaranteed = [item for item in scores if item["guaranteed_reception"]]
    pool = guaranteed or scores
    selected = min(pool, key=lambda item: (item["score"],
                                           -item["fim_proxy_per_s"],
                                           item["point"]))
    fim_choice = max(scores, key=lambda item: (item["fim_proxy_per_s"],
                                               -item["score"]))
    return {
        "method": "set_worst_case_radius_per_action_time",
        "selected_point": selected["point"],
        "selected": selected,
        "fim_baseline_point": fim_choice["point"],
        "candidate_count": len(scores),
        "guaranteed_candidate_count": len(guaranteed),
        "candidates": scores,
        "candidate_regions": candidate_regions,
        "region": region,
        "config": asdict(config),
        "limitations": [
            "源物理圆域用外切正多边形保守近似。",
            "保证接收域是圆交集的内近似；可能接收域是圆盘Minkowski和的外近似。",
            "最坏情形在有限边界场景和误差端点上计算，不声称连续全局最优。",
            "FIM只作排序基准，最终选择使用集合评分。",
        ],
    }


def plan_second_point(first_observation, *, current_channel=None,
                      config=Q2Config()):
    if first_observation.result != "direction":
        raise ValueError("Q2需要第一检测点返回 direction。")
    region = build_region_from_observations(
        [first_observation], error_deg=config.error_deg,
        arena_radius=config.arena_radius,
        max_receive_radius=config.max_receive_radius,
        circle_sides=config.circle_sides,
    )
    return plan_measurement(
        region, [first_observation],
        current_position=first_observation.position,
        current_channel=current_channel or first_observation.channel,
        target_channel=first_observation.channel,
        config=config,
    )
