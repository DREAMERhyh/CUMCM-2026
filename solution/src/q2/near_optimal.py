"""Sampled 5%/10% near-optimal detector regions for Q2."""

import math

from q1.geometry import hull

from .continuous_fim import project_to_polygon


def _polygon_area(vertices):
    if len(vertices) < 3:
        return 0.0
    return abs(sum(
        first[0] * second[1] - first[1] * second[0]
        for first, second in zip(vertices, vertices[1:] + vertices[:1])
    )) / 2.0


def local_sample_points(center, feasible_vertices, mode="online"):
    """Return deterministic local samples clipped to the feasible polygon."""
    if mode == "off":
        return [tuple(center)]
    if mode == "online":
        radii, direction_count = (20.0, 40.0), 8
    elif mode == "offline":
        radii, direction_count = (10.0, 20.0, 40.0, 60.0, 80.0), 16
    else:
        raise ValueError("近优域模式必须为 off、online 或 offline。")
    raw = [tuple(center)]
    for radius in radii:
        for index in range(direction_count):
            angle = 2.0 * math.pi * index / direction_count
            raw.append((center[0] + radius * math.cos(angle),
                        center[1] + radius * math.sin(angle)))
    unique = {}
    for point in raw:
        projected = project_to_polygon(point, feasible_vertices)
        unique[(round(projected[0], 8), round(projected[1], 8))] = projected
    return list(unique.values())


def _local_bounds(vertices, origin, bearing_deg):
    if not vertices:
        return None
    angle = math.radians(bearing_deg)
    forward = math.cos(angle), math.sin(angle)
    lateral = -forward[1], forward[0]
    local = []
    for point in vertices:
        delta = point[0] - origin[0], point[1] - origin[1]
        local.append((delta[0] * forward[0] + delta[1] * forward[1],
                      delta[0] * lateral[0] + delta[1] * lateral[1]))
    return {
        "forward_m": [min(item[0] for item in local),
                      max(item[0] for item in local)],
        "lateral_m": [min(item[1] for item in local),
                      max(item[1] for item in local)],
    }


def build_near_optimal_regions(reference, scored_samples, *,
                               first_position, first_bearing_deg,
                               tolerances=(0.05, 0.10),
                               time_slack_s=10.0, mode="online",
                               timed_out=False):
    """Build sampled convex-hull visual approximations around one solution.

    Only sample points are verified against the objective.  Convex-hull
    interiors are visual approximations and are not continuous certificates.
    """
    if any(value <= 0.0 for value in tolerances):
        raise ValueError("近优域比例必须为正数。")
    if time_slack_s < 0.0:
        raise ValueError("近优域时间松弛不能为负数。")
    usable = [item for item in scored_samples
              if item.get("guaranteed_reception")
              and math.isfinite(item.get("worst_case_radius_m", math.inf))
              and math.isfinite(item.get("action_time_s", math.inf))]
    regions = {}
    for tolerance in tolerances:
        radius_limit = reference["worst_case_radius_m"] * (1.0 + tolerance)
        time_limit = reference["action_time_s"] + time_slack_s
        qualified = [item for item in usable
                     if item["worst_case_radius_m"] <= radius_limit + 1e-9
                     and item["action_time_s"] <= time_limit + 1e-9]
        vertices = hull([tuple(item["point"]) for item in qualified])
        status = "bounded" if len(vertices) >= 3 and _polygon_area(vertices) > 1e-8 else "degenerate"
        key = f"{int(round(100 * tolerance))}pct"
        regions[key] = {
            "status": status,
            "relative_radius_tolerance": tolerance,
            "time_slack_s": time_slack_s,
            "radius_limit_m": radius_limit,
            "action_time_limit_s": time_limit,
            "components": ([{"vertices": vertices}]
                           if status == "bounded" else []),
            "boundary_points": vertices,
            "area_m2": _polygon_area(vertices),
            "qualified_sample_count": len(qualified),
            "evaluated_sample_count": len(usable),
            "local_bounds": _local_bounds(
                vertices, first_position, first_bearing_deg
            ),
        }
    return {
        "status": "partial" if timed_out else "ok",
        "name": "sampled_near_optimal_region",
        "mode": mode,
        "objective": "worst_case_radius_m_then_action_time_s",
        "reference_point": tuple(reference["point"]),
        "reference_radius_m": reference["worst_case_radius_m"],
        "reference_action_time_s": reference["action_time_s"],
        "regions": regions,
        "timed_out": timed_out,
        "approximation": {
            "kind": "convex_hull_of_verified_local_samples",
            "continuous_certificate": False,
            "warning": "仅采样点满足阈值；凸包内部是绘图近似，不是连续保证。",
        },
    }
