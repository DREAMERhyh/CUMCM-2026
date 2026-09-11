"""Continuous candidate regions and deterministic search points for B-Q2."""

import math

from q1.geometry import hull


def _clip_halfplane(polygon, plane, tolerance=1e-9):
    """Clip a convex polygon by ``a*x+b*y<=c``."""
    if not polygon:
        return []
    a, b, c = plane
    output = []
    for first, second in zip(polygon, polygon[1:]+polygon[:1]):
        f_first = a*first[0] + b*first[1] - c
        f_second = a*second[0] + b*second[1] - c
        first_inside = f_first <= tolerance
        second_inside = f_second <= tolerance
        if first_inside:
            output.append(first)
        if first_inside != second_inside:
            denominator = f_first-f_second
            if abs(denominator) > 1e-15:
                ratio = f_first/denominator
                output.append((first[0]+ratio*(second[0]-first[0]),
                               first[1]+ratio*(second[1]-first[1])))
    return output


def _clip_many(polygon, planes):
    for plane in planes:
        polygon = _clip_halfplane(polygon, plane)
        if not polygon:
            break
    return hull(polygon)


def _inner_circle_polygon(center, radius, sides):
    return [(center[0]+radius*math.cos(2*math.pi*k/sides),
             center[1]+radius*math.sin(2*math.pi*k/sides))
            for k in range(sides)]


def _inner_circle_planes(center, radius, sides):
    support = radius*math.cos(math.pi/sides)
    for k in range(sides):
        angle = 2*math.pi*(k+0.5)/sides
        nx, ny = math.cos(angle), math.sin(angle)
        yield nx, ny, support+nx*center[0]+ny*center[1]


def _summary(vertices, *, kind, relation, radius, sides, definition):
    vertices = hull(vertices)
    area = 0.0
    if len(vertices) >= 3:
        area = abs(sum(p[0]*q[1]-p[1]*q[0]
                       for p, q in zip(vertices, vertices[1:]+vertices[:1])))/2
    status = "bounded" if len(vertices) >= 3 and area > 1e-8 else "empty"
    return {
        "status": status,
        "vertices": vertices if status == "bounded" else [],
        "area_m2": area if status == "bounded" else 0.0,
        "definition": definition,
        "radius_m": radius,
        "approximation": {
            "kind": kind,
            "relation_to_exact_region": relation,
            "circle_sides": sides,
        },
    }


def build_candidate_regions(source_region, *, min_receive_radius=1000.0,
                            max_receive_radius=1500.0, circle_sides=72):
    """Return continuous second-detector regions as polygon approximations.

    The guaranteed region is ``intersection_{g in P} B(g, R_min)``.  For a
    convex polygon P it suffices to impose the disks centered at its vertices.
    Inscribed regular polygons produce a conservative inner approximation: any
    returned point is genuinely within ``R_min`` of every source hypothesis.

    The possible region is ``P + B(0, R_max)``.  Finite support directions give
    a conservative outer approximation suitable for plotting its full extent.
    """
    if source_region.get("status") != "bounded":
        raise ValueError("Q2候选区域需要有界源位置区域。")
    if min_receive_radius <= 0 or max_receive_radius < min_receive_radius:
        raise ValueError("接收半径范围不合法。")
    if circle_sides < 16:
        raise ValueError("候选区域圆近似边数至少为16。")
    source_vertices = [tuple(point) for point in source_region["vertices"]]
    if not source_vertices:
        raise ValueError("源位置区域没有可用顶点。")

    guaranteed = _inner_circle_polygon(source_vertices[0],
                                       min_receive_radius, circle_sides)
    for center in source_vertices[1:]:
        guaranteed = _clip_many(
            guaranteed,
            _inner_circle_planes(center, min_receive_radius, circle_sides),
        )
        if not guaranteed:
            break
    guaranteed_summary = _summary(
        guaranteed,
        kind="intersection_of_inscribed_regular_polygons",
        relation="inner",
        radius=min_receive_radius,
        sides=circle_sides,
        definition="max_{g in source_region} distance(sensor,g) <= min_receive_radius",
    )
    guaranteed_summary["constraint_centers"] = source_vertices

    margin = 1.1*max_receive_radius
    xs = [point[0] for point in source_vertices]
    ys = [point[1] for point in source_vertices]
    possible = [(min(xs)-margin, min(ys)-margin),
                (max(xs)+margin, min(ys)-margin),
                (max(xs)+margin, max(ys)+margin),
                (min(xs)-margin, max(ys)+margin)]
    possible_planes = []
    for k in range(circle_sides):
        angle = 2*math.pi*k/circle_sides
        nx, ny = math.cos(angle), math.sin(angle)
        support = max(nx*x+ny*y for x, y in source_vertices)
        possible_planes.append((nx, ny, support+max_receive_radius))
    possible = _clip_many(possible, possible_planes)
    possible_summary = _summary(
        possible,
        kind="finite_support_minkowski_outer_polygon",
        relation="outer",
        radius=max_receive_radius,
        sides=circle_sides,
        definition="distance(sensor, source_region) <= max_receive_radius",
    )
    return {
        "guaranteed_reception": guaranteed_summary,
        "possible_reception": possible_summary,
    }


def generate_candidates(region, current_position, first_bearing_deg,
                        *, guaranteed_region=None,
                        forward_steps=(100.0, 250.0, 500.0, 750.0),
                        center_radii=(250.0, 500.0, 750.0),
                        center_angles=8):
    if region.get("status") != "bounded":
        raise ValueError("Q2候选生成需要有界物理定位区域。")
    theta = math.radians(first_bearing_deg)
    u = (math.cos(theta), math.sin(theta))
    n = (-u[1], u[0])
    x0, y0 = current_position
    center = tuple(region["minimum_enclosing_circle"]["center"])
    raw = []
    for step in forward_steps:
        for lateral in (0.0, -0.5*step, 0.5*step, -step, step):
            raw.append((x0 + step*u[0] + lateral*n[0],
                        y0 + step*u[1] + lateral*n[1]))
    raw.append(((x0+center[0])/2, (y0+center[1])/2))
    for radius in center_radii:
        for k in range(center_angles):
            angle = 2*math.pi*k/center_angles
            raw.append((center[0]+radius*math.cos(angle),
                        center[1]+radius*math.sin(angle)))
    if guaranteed_region and guaranteed_region.get("status") == "bounded":
        polygon = guaranteed_region["vertices"]
        centroid = (sum(point[0] for point in polygon)/len(polygon),
                    sum(point[1] for point in polygon)/len(polygon))
        raw.append(centroid)
    unique = {}
    for point in raw:
        if all(math.isfinite(v) and abs(v) <= 2_000_000 for v in point):
            unique[(round(point[0], 9), round(point[1], 9))] = point
    return list(unique.values())
