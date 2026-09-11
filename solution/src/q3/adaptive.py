"""Adaptive localisation and posterior-region clearing helpers for Q3."""

import math

from q1.geometry import contains


DEFAULT_CLEAR_GRID_SPACING_M = 27.0
CLEAR_RADIUS_M = 20.0


def _point_segment_distance(point, first, second):
    dx, dy = second[0] - first[0], second[1] - first[1]
    denominator = dx * dx + dy * dy
    if denominator <= 1e-15:
        return math.dist(point, first)
    ratio = ((point[0] - first[0]) * dx
             + (point[1] - first[1]) * dy) / denominator
    ratio = max(0.0, min(1.0, ratio))
    projection = first[0] + ratio * dx, first[1] + ratio * dy
    return math.dist(point, projection)


def _distance_to_polygon(point, vertices, planes):
    if contains(planes, point):
        return 0.0
    return min(
        _point_segment_distance(point, first, second)
        for first, second in zip(vertices, vertices[1:] + vertices[:1])
    )


def posterior_clear_points(
        region, *, spacing_m=DEFAULT_CLEAR_GRID_SPACING_M):
    """Return a square-lattice cover of the current convex source region.

    Every source point lies within ``spacing_m/sqrt(2)`` of an infinite
    lattice point.  Keeping lattice points whose distance to the polygon is no
    larger than that value preserves this cover while removing most points in
    the empty part of an axis-aligned bounding box.  The default 27 m spacing
    gives a 19.092 m covering radius, leaving about 0.908 m of geometric
    margin below the 20 m clearing radius.
    """
    if region.get("status") != "bounded":
        raise ValueError("后验清除网格需要有界区域。")
    if not math.isfinite(spacing_m) or spacing_m <= 0.0:
        raise ValueError("清除网格间距必须为正数。")
    vertices = [tuple(point) for point in region["vertices"]]
    planes = region["planes"]
    xs, ys = [point[0] for point in vertices], [point[1] for point in vertices]
    ix_min = math.floor(min(xs) / spacing_m) - 1
    ix_max = math.ceil(max(xs) / spacing_m) + 1
    iy_min = math.floor(min(ys) / spacing_m) - 1
    iy_max = math.ceil(max(ys) / spacing_m) + 1
    cover_radius = spacing_m / math.sqrt(2.0) + 1e-7
    points = []
    for iy in range(iy_min, iy_max + 1):
        for ix in range(ix_min, ix_max + 1):
            point = ix * spacing_m, iy * spacing_m
            if _distance_to_polygon(point, vertices, planes) <= cover_radius:
                points.append(point)
    return points


def nearest_neighbor_order(points, start):
    """Order a small finite clear cover from the robot's current position."""
    remaining = list(dict.fromkeys(tuple(point) for point in points))
    ordered = []
    current = tuple(start)
    while remaining:
        index = min(range(len(remaining)),
                    key=lambda item: (math.dist(current, remaining[item]),
                                      remaining[item]))
        current = remaining.pop(index)
        ordered.append(current)
    return ordered


def worst_case_clear_cost(points, start):
    """Return virtual seconds if the source is cleared at the last point."""
    ordered = nearest_neighbor_order(points, start)
    distance = 0.0
    current = tuple(start)
    for point in ordered:
        distance += math.dist(current, point)
        current = point
    count = len(ordered)
    return distance / 5.0 + 3.0 * count + (2.0 if count else 0.0)


def radius_clear_cost_proxy(
        radius_m, *, spacing_m=DEFAULT_CLEAR_GRID_SPACING_M):
    """Conservative, monotone disk-cover proxy used for measure/clear choice."""
    if radius_m <= 0.0:
        return 5.0
    side = math.ceil(2.0 * radius_m / spacing_m) + 2
    point_count = side * side
    return point_count * (spacing_m / 5.0 + 3.0) + 2.0


def measurement_is_worthwhile(current_radius_m, predicted_radius_m,
                              action_time_s, *, margin_s=10.0,
                              spacing_m=DEFAULT_CLEAR_GRID_SPACING_M,
                              current_clear_cost_s=None):
    """One-step rolling comparison between another bearing and grid clearing."""
    clear_now = (radius_clear_cost_proxy(current_radius_m,
                                         spacing_m=spacing_m)
                 if current_clear_cost_s is None
                 else current_clear_cost_s)
    if not math.isfinite(predicted_radius_m):
        return False
    ratio = min(1.0, max(0.0, predicted_radius_m/current_radius_m))
    predicted_clear = max(5.0, clear_now*ratio*ratio)
    measure_then_clear = (
        action_time_s
        + predicted_clear
    )
    return measure_then_clear + margin_s < clear_now
