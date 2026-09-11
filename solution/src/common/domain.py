"""Conservative physical priors used after Q1's pure-bearing analysis.

Circles are represented by circumscribed regular polygons.  The polygon is an
outer approximation, so it never removes a physically possible source merely
because of discretisation.
"""

import math

from q1.geometry import bearing_planes, intersect_halfplanes

from .models import BearingObservation


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


def build_region_from_observations(observations, *, error_deg=1.005,
                                   arena_radius=1800.0,
                                   max_receive_radius=1500.0,
                                   circle_sides=32):
    """Return a conservative bounded region from successful bearings.

    A direction response proves that the source is within its unknown receive
    radius, hence certainly within the stated maximum radius.  The 5 m ``near``
    hole is intentionally not subtracted because doing so would be non-convex.
    """
    observations = list(observations)
    planes = circle_outer_planes((0.0, 0.0), arena_radius, circle_sides)
    direction_count = 0
    for obs in observations:
        if obs.result != "direction":
            continue
        direction_count += 1
        planes.extend(circle_outer_planes(obs.position, max_receive_radius,
                                          circle_sides))
        planes.extend(bearing_planes(obs.position, obs.bearing_deg, error_deg))
    if direction_count == 0:
        raise ValueError("至少需要一次 direction 观测才能构造定位区域。")
    region = intersect_halfplanes(planes)
    region["planes"] = planes
    region["observation_count"] = direction_count
    region["approximation"] = {
        "kind": "circumscribed_regular_polygon",
        "circle_sides": circle_sides,
        "conservative": True,
    }
    return region


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
