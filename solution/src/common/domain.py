"""Conservative source regions used after Q1's pure-bearing analysis.

The default ``new`` Q2 geometry starts from a coarse circumscribed regular
polygon, then adds endpoint and radial-error tangents conservatively.  The
selectable ``legacy`` geometry keeps the original fixed circumscribed regular
polygons.  Both branches contain every corresponding disk.
"""

import math

from q1.geometry import bearing_planes, intersect_halfplanes

from .models import BearingObservation


_GEOMETRY_TOL = 1e-7
_MAX_REFINEMENT_ROUNDS = 8
_Q2_VERSIONS = ("new", "legacy")


def _validate_q2_version(q2_version):
    if q2_version not in _Q2_VERSIONS:
        raise ValueError("Q2版本必须为new或legacy。")


def circle_outer_planes(center, radius, sides=32):
    if radius <= 0 or sides < 8:
        raise ValueError("圆半径须为正且外切多边形边数至少为8。")
    cx, cy = center
    planes = []
    for k in range(sides):
        angle = 2*math.pi*k/sides
        nx, ny = math.cos(angle), math.sin(angle)
        planes.append((nx, ny, radius + nx*cx + ny*cy))
    return planes


def _normalize_plane(plane):
    a, b, c = plane
    length = math.hypot(a, b)
    if length <= 0.0:
        raise ValueError("圆弧细化不能使用零法向量半平面。")
    return a/length, b/length, c/length


def _append_unique_planes(planes, candidates, limit=None):
    """Append numerically distinct normalized planes deterministically."""
    normalized = [_normalize_plane(plane) for plane in planes]
    added = 0
    for candidate in candidates:
        candidate = _normalize_plane(candidate)
        if any(
            abs(candidate[0]-plane[0]) <= 1e-11
            and abs(candidate[1]-plane[1]) <= 1e-11
            and abs(candidate[2]-plane[2]) <= 1e-7
            for plane in normalized
        ):
            continue
        if limit is not None and added >= limit:
            break
        planes.append(candidate)
        normalized.append(candidate)
        added += 1
    return added


def _line_circle_intersections(plane, center, radius):
    a, b, c = _normalize_plane(plane)
    offset = c-a*center[0]-b*center[1]
    if abs(offset) > radius + _GEOMETRY_TOL:
        return []
    foot = center[0]+a*offset, center[1]+b*offset
    half = math.sqrt(max(0.0, radius*radius-offset*offset))
    tangent = -b, a
    if half <= _GEOMETRY_TOL:
        return [foot]
    return [
        (foot[0]+half*tangent[0], foot[1]+half*tangent[1]),
        (foot[0]-half*tangent[0], foot[1]-half*tangent[1]),
    ]


def _circle_circle_intersections(first, second):
    first_center, first_radius = first
    second_center, second_radius = second
    dx = second_center[0]-first_center[0]
    dy = second_center[1]-first_center[1]
    distance = math.hypot(dx, dy)
    if distance <= _GEOMETRY_TOL:
        return []
    if distance > first_radius+second_radius+_GEOMETRY_TOL:
        return []
    if distance < abs(first_radius-second_radius)-_GEOMETRY_TOL:
        return []
    along = (
        first_radius*first_radius-second_radius*second_radius
        + distance*distance
    )/(2.0*distance)
    height = math.sqrt(max(0.0, first_radius*first_radius-along*along))
    base = (
        first_center[0]+along*dx/distance,
        first_center[1]+along*dy/distance,
    )
    perpendicular = -dy/distance, dx/distance
    if height <= _GEOMETRY_TOL:
        return [base]
    return [
        (base[0]+height*perpendicular[0],
         base[1]+height*perpendicular[1]),
        (base[0]-height*perpendicular[0],
         base[1]-height*perpendicular[1]),
    ]


def _satisfies_exact_constraints(point, linear_planes, circles):
    for plane in linear_planes:
        a, b, c = _normalize_plane(plane)
        if a*point[0]+b*point[1] > c+1e-6:
            return False
    for center, radius in circles:
        if math.dist(point, center) > radius+1e-6:
            return False
    return True


def _circle_tangent_plane(center, radius, point):
    dx, dy = point[0]-center[0], point[1]-center[1]
    distance = math.hypot(dx, dy)
    if distance <= _GEOMETRY_TOL:
        return None
    nx, ny = dx/distance, dy/distance
    return nx, ny, radius+nx*center[0]+ny*center[1]


def _endpoint_tangent_planes(linear_planes, circles):
    """Use exact feasible boundary intersections as tangent seed points."""
    tangents = []
    for center, radius in circles:
        for line in linear_planes:
            for point in _line_circle_intersections(
                    line, center, radius):
                if _satisfies_exact_constraints(
                        point, linear_planes, circles):
                    tangent = _circle_tangent_plane(center, radius, point)
                    if tangent is not None:
                        tangents.append(tangent)
    for first_index, first in enumerate(circles):
        for second in circles[first_index+1:]:
            for point in _circle_circle_intersections(first, second):
                if not _satisfies_exact_constraints(
                        point, linear_planes, circles):
                    continue
                for center, radius in (first, second):
                    tangent = _circle_tangent_plane(center, radius, point)
                    if tangent is not None:
                        tangents.append(tangent)
    return tangents


def _radial_target(radius, sides):
    """Target the radial error of a full regular polygon with 2*sides."""
    return radius*(1.0/math.cos(math.pi/(2.0*sides))-1.0)


def _adaptive_circle_intersection(linear_planes, circles, circle_sides,
                                  base_planes=None):
    """Return a nested conservative polygon with locally refined tangents."""
    if circle_sides < 8:
        raise ValueError("圆的初始外切多边形边数至少为8。")
    linear_planes = list(linear_planes)
    circles = [(tuple(center), float(radius)) for center, radius in circles]
    if base_planes is None:
        planes = list(linear_planes)
        for center, radius in circles:
            planes.extend(circle_outer_planes(center, radius, circle_sides))
    else:
        planes = list(base_planes)

    endpoint_candidates = _endpoint_tangent_planes(linear_planes, circles)
    endpoint_count = _append_unique_planes(planes, endpoint_candidates)
    region = intersect_halfplanes(planes)

    adaptive_count = 0
    rounds = 0
    maximum_adaptive = max(8, 2*circle_sides*len(circles))
    for round_index in range(_MAX_REFINEMENT_ROUNDS):
        if region.get("status") != "bounded":
            break
        candidates = []
        for center, radius in circles:
            target = _radial_target(radius, circle_sides)
            for vertex in region["vertices"]:
                if math.dist(vertex, center)-radius > target+1e-7:
                    tangent = _circle_tangent_plane(center, radius, vertex)
                    if tangent is not None:
                        candidates.append(tangent)
        remaining = maximum_adaptive-adaptive_count
        added = _append_unique_planes(
            planes, candidates, limit=max(0, remaining)
        )
        if added == 0:
            break
        adaptive_count += added
        rounds = round_index+1
        region = intersect_halfplanes(planes)
        if adaptive_count >= maximum_adaptive:
            break

    details = []
    target_met = region.get("status") == "bounded"
    for center, radius in circles:
        maximum_excess = (
            max(math.dist(vertex, center)-radius
                for vertex in region.get("vertices", ()))
            if region.get("vertices") else float("inf")
        )
        target = _radial_target(radius, circle_sides)
        met = maximum_excess <= target+1e-6
        target_met &= met
        details.append({
            "center": center,
            "radius_m": radius,
            "target_radial_excess_m": target,
            "actual_max_vertex_excess_m": max(0.0, maximum_excess),
            "target_met": met,
        })
    region["planes"] = planes
    region["approximation"] = {
        "kind": "adaptive_circumscribed_polygon",
        "q2_version": "new",
        "circle_sides": circle_sides,
        "effective_full_circle_sides": 2*circle_sides,
        "endpoint_tangent_count": endpoint_count,
        "adaptive_tangent_count": adaptive_count,
        "refinement_rounds": rounds,
        "target_met": target_met,
        "circle_details": details,
        "conservative": True,
    }
    return region


def build_region_from_observations(observations, *, error_deg=1.005,
                                   arena_radius=1800.0,
                                   max_receive_radius=1500.0,
                                   circle_sides=32,
                                   q2_version="new"):
    """Return a conservative bounded region from successful bearings.

    A direction response proves that the source is within its unknown receive
    radius, hence certainly within the stated maximum radius.  The 5 m ``near``
    hole is intentionally not subtracted because doing so would be non-convex.
    """
    _validate_q2_version(q2_version)
    observations = list(observations)
    linear_planes = []
    circles = [((0.0, 0.0), arena_radius)]
    base_planes = circle_outer_planes(
        (0.0, 0.0), arena_radius, circle_sides
    )
    direction_count = 0
    for obs in observations:
        if obs.result != "direction":
            continue
        direction_count += 1
        circles.append((obs.position, max_receive_radius))
        bearing = bearing_planes(
            obs.position, obs.bearing_deg, error_deg
        )
        base_planes.extend(circle_outer_planes(
            obs.position, max_receive_radius, circle_sides
        ))
        base_planes.extend(bearing)
        linear_planes.extend(bearing)
    if direction_count == 0:
        raise ValueError("至少需要一次 direction 观测才能构造定位区域。")
    if q2_version == "new":
        region = _adaptive_circle_intersection(
            linear_planes, circles, circle_sides,
            base_planes=base_planes,
        )
    else:
        region = intersect_halfplanes(base_planes)
        region["planes"] = base_planes
        region["approximation"] = {
            "kind": "circumscribed_regular_polygon",
            "q2_version": "legacy",
            "circle_sides": circle_sides,
            "conservative": True,
        }
    region["observation_count"] = direction_count
    return region


def extend_region_with_observation(region, observation, *, error_deg=1.005,
                                   max_receive_radius=1500.0,
                                   circle_sides=32,
                                   q2_version="new"):
    """Intersect a region with one observation using the selected Q2 version."""
    _validate_q2_version(q2_version)
    if region.get("status") != "bounded":
        raise ValueError("新增观测需要已有的有界源位置区域。")
    if observation.result != "direction":
        raise ValueError("新增观测必须包含有效示向度。")
    bearing = bearing_planes(
        observation.position, observation.bearing_deg, error_deg
    )
    region_version = region.get("approximation", {}).get("q2_version")
    if region_version is not None and region_version != q2_version:
        raise ValueError("已有区域与新增观测使用的Q2版本不一致。")
    if q2_version == "legacy":
        planes = list(region["planes"])
        planes.extend(circle_outer_planes(
            observation.position, max_receive_radius, circle_sides
        ))
        planes.extend(bearing)
        posterior = intersect_halfplanes(planes)
        posterior["planes"] = planes
        posterior["observation_count"] = (
            region.get("observation_count", 0)+1
        )
        posterior["approximation"] = {
            "kind": "circumscribed_regular_polygon",
            "q2_version": "legacy",
            "circle_sides": circle_sides,
            "conservative": True,
        }
        return posterior

    base_planes = [
        *region["planes"],
        *circle_outer_planes(
            observation.position, max_receive_radius, circle_sides
        ),
        *bearing,
    ]
    posterior = _adaptive_circle_intersection(
        [*region["planes"], *bearing],
        [(observation.position, max_receive_radius)],
        circle_sides,
        base_planes=base_planes,
    )
    posterior["observation_count"] = region.get("observation_count", 0)+1
    return posterior


def representative_points(vertices, limit=12):
    """Deterministic boundary scenarios plus a centroid for robust scoring."""
    points = list(vertices)
    if not points:
        return []
    expanded = []
    for p, q in zip(points, points[1:]+points[:1]):
        expanded.extend([p, ((p[0]+q[0])/2, (p[1]+q[1])/2)])
    centroid = (sum(p[0] for p in points)/len(points),
                sum(p[1] for p in points)/len(points))
    expanded.append(centroid)
    if len(expanded) <= limit:
        return expanded
    indices = [round(i*(len(expanded)-1)/(limit-1)) for i in range(limit)]
    return [expanded[i] for i in indices]


def max_vertex_distance(point, vertices):
    return max(math.dist(point, vertex) for vertex in vertices)
