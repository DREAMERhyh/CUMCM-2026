"""Certified coverage constructions for mixed omni/directional Q4 sources."""

import math


def grid121():
    """Return the historical 500 m square-grid baseline in snake order."""
    rows = []
    for row, y_index in enumerate(range(-5, 6)):
        xs = range(-5, 6) if row % 2 == 0 else range(5, -6, -1)
        rows.extend((500.0*x, 500.0*y_index) for x in xs)
    return [(0.0, 0.0)] + [point for point in rows if point != (0.0, 0.0)]


def _point_segment_distance(point, first, second):
    dx, dy = second[0]-first[0], second[1]-first[1]
    denominator = dx*dx + dy*dy
    if denominator <= 1e-15:
        return math.dist(point, first)
    ratio = ((point[0]-first[0])*dx
             + (point[1]-first[1])*dy) / denominator
    ratio = max(0.0, min(1.0, ratio))
    projection = first[0]+ratio*dx, first[1]+ratio*dy
    return math.dist(point, projection)


def _origin_in_triangle(triangle, tolerance=1e-9):
    signs = []
    for first, second in zip(triangle, triangle[1:]+triangle[:1]):
        signs.append((second[0]-first[0])*(-first[1])
                     - (second[1]-first[1])*(-first[0]))
    return min(signs) >= -tolerance or max(signs) <= tolerance


def _triangle_intersects_disk(triangle, radius):
    if any(math.hypot(*point) <= radius+1e-9 for point in triangle):
        return True
    if _origin_in_triangle(triangle):
        return True
    return min(
        _point_segment_distance((0.0, 0.0), first, second)
        for first, second in zip(triangle, triangle[1:]+triangle[:1])
    ) <= radius+1e-9


def _nearest_neighbor_order(points, start=(0.0, 0.0)):
    remaining = sorted(set(points))
    ordered = []
    current = tuple(start)
    while remaining:
        index = min(
            range(len(remaining)),
            key=lambda item: (math.dist(current, remaining[item]),
                              remaining[item]),
        )
        current = remaining.pop(index)
        ordered.append(current)
    return ordered


def _improve_open_path(points):
    """Deterministic 2-opt for the fixed scan path while keeping its start."""
    route = list(points)
    while len(route) >= 3:
        best_delta = -1e-9
        best_pair = None
        for first in range(1, len(route)-1):
            for last in range(first+1, len(route)):
                old = math.dist(route[first-1], route[first])
                new = math.dist(route[first-1], route[last])
                if last+1 < len(route):
                    old += math.dist(route[last], route[last+1])
                    new += math.dist(route[first], route[last+1])
                delta = new-old
                candidate = (delta, first, last)
                if delta < best_delta and (
                        best_pair is None or candidate < best_pair):
                    best_delta = delta
                    best_pair = candidate
        if best_pair is None:
            break
        _, first, last = best_pair
        route[first:last+1] = reversed(route[first:last+1])
    return route


def triangular_scan_mesh(*, spacing=900.0, arena_radius=1800.0,
                         min_receive_radius=1000.0):
    """Return a triangular-lattice discovery certificate and its cells.

    Every selected equilateral triangle has diameter ``spacing``.  Every
    source in the target disk lies in one selected triangle, hence all three
    of that triangle's vertices are within ``spacing`` of the source.  Since
    the source is a convex combination of those vertices, every closed
    emission half-plane through the source contains at least one vertex.
    Thus ``spacing <= min_receive_radius`` certifies both omni and directional
    discovery when every returned point is tested.
    """
    if not (math.isfinite(spacing) and spacing > 0.0):
        raise ValueError("三角扫描网边长必须为正数。")
    if not (math.isfinite(arena_radius) and arena_radius > 0.0):
        raise ValueError("目标圆半径必须为正数。")
    if spacing > min_receive_radius:
        raise ValueError("三角扫描网边长不能超过最小有效接收半径。")

    height = spacing*math.sqrt(3.0)/2.0

    def lattice(i, j):
        return spacing*(i+0.5*j), height*j

    limit = math.ceil((arena_radius+spacing)/height)+2
    triangles = []
    vertices = set()
    for i in range(-limit, limit+1):
        for j in range(-limit, limit+1):
            candidates = (
                (lattice(i, j), lattice(i+1, j), lattice(i, j+1)),
                (lattice(i+1, j+1), lattice(i, j+1), lattice(i+1, j)),
            )
            for triangle in candidates:
                if not _triangle_intersects_disk(triangle, arena_radius):
                    continue
                triangle = tuple(
                    (round(point[0], 12), round(point[1], 12))
                    for point in triangle
                )
                triangles.append(triangle)
                vertices.update(triangle)

    origin = (0.0, 0.0)
    vertices.discard(origin)
    points = _improve_open_path([
        origin, *_nearest_neighbor_order(vertices, origin),
    ])
    return points, triangles


def triangular37():
    """Return the 37-point, 900 m triangular discovery scan."""
    points, _ = triangular_scan_mesh()
    if len(points) != 37:
        raise RuntimeError(f"默认三角扫描网应含37点，实际为{len(points)}点。")
    return points


def four_sided_points(center, radius, rho=200.0):
    """Historical fixed-offset square certificate."""
    if rho/math.sqrt(2) <= radius or rho+radius > 1000.0:
        return []
    x, y = center
    return [(x+rho, y), (x, y+rho), (x-rho, y), (x, y-rho)]


def adaptive_four_sided_points(center, radius, *, preferred_rho=200.0,
                               min_receive_radius=1000.0):
    """Return a compact four-point certificate with a radius-adaptive offset.

    The square must contain the complete enclosing disk and every probe must
    remain within the minimum receive radius of every possible source:
    ``sqrt(2)*radius < rho <= min_receive_radius-radius``.
    """
    if radius < 0.0:
        raise ValueError("定位圆半径不能为负数。")
    lower = math.sqrt(2.0)*radius
    upper = min_receive_radius-radius
    if lower >= upper-1e-9:
        return []
    gap = upper-lower
    rho = max(preferred_rho, lower+min(1.0, 0.05*gap))
    rho = min(rho, upper)
    if rho <= lower:
        return []
    x, y = center
    return [(x+rho, y), (x, y+rho), (x-rho, y), (x, y-rho)]


def certified_probe_points(region, *, spacing=900.0,
                           min_receive_radius=1000.0, phase_index=0):
    """Return a finite direction-safe probe cover for a bounded posterior.

    A compact four-sided certificate is preferred when it exists.  For a
    larger posterior, a translated triangular lattice covers the complete
    posterior bounding box.  Every possible source lies in one retained
    equilateral triangle; all three vertices are within ``spacing`` and at
    least one vertex lies in every closed emission half-plane through the
    source.  The returned points may therefore be ordered adaptively without
    weakening the certificate, provided all remaining points stay available.
    """
    if region.get("status") != "bounded":
        raise ValueError("定向探测组需要有界位置后验。")
    if not (math.isfinite(spacing) and 0.0 < spacing <= min_receive_radius):
        raise ValueError("定向三角探测网边长必须位于(0,最小接收半径]。")
    if phase_index < 0:
        raise ValueError("探测网相位编号不能为负数。")

    circle = region["minimum_enclosing_circle"]
    center = tuple(circle["center"])
    compact = adaptive_four_sided_points(
        center, circle["radius"],
        min_receive_radius=min_receive_radius,
    )
    if compact:
        return compact, "four_sided"

    vertices = [tuple(point) for point in region["vertices"]]
    min_x = min(point[0] for point in vertices)
    max_x = max(point[0] for point in vertices)
    min_y = min(point[1] for point in vertices)
    max_y = max(point[1] for point in vertices)
    height = spacing*math.sqrt(3.0)/2.0
    # Alternate lattice phases between refinements so a later bundle does not
    # mechanically repeat the same observations after the region changes only
    # slightly.  Translation preserves the triangular coverage proof.
    phase = phase_index % 3
    origin_x = center[0] + phase*spacing/3.0
    origin_y = center[1] + phase*height/3.0

    def lattice(i, j):
        return (
            origin_x + spacing*(i+0.5*j),
            origin_y + height*j,
        )

    j_min = math.floor((min_y-origin_y)/height)-2
    j_max = math.ceil((max_y-origin_y)/height)+2
    selected = set()
    for j in range(j_min, j_max+1):
        horizontal_shift = 0.5*j*spacing
        i_min = math.floor(
            (min_x-origin_x-horizontal_shift)/spacing
        )-2
        i_max = math.ceil(
            (max_x-origin_x-horizontal_shift)/spacing
        )+2
        for i in range(i_min, i_max+1):
            triangles = (
                (lattice(i, j), lattice(i+1, j), lattice(i, j+1)),
                (lattice(i+1, j+1), lattice(i, j+1), lattice(i+1, j)),
            )
            for triangle in triangles:
                tri_min_x = min(point[0] for point in triangle)
                tri_max_x = max(point[0] for point in triangle)
                tri_min_y = min(point[1] for point in triangle)
                tri_max_y = max(point[1] for point in triangle)
                if (tri_max_x < min_x-1e-9 or tri_min_x > max_x+1e-9
                        or tri_max_y < min_y-1e-9
                        or tri_min_y > max_y+1e-9):
                    continue
                selected.update(
                    (round(point[0], 12), round(point[1], 12))
                    for point in triangle
                )
    if not selected:
        raise RuntimeError("未能为有界后验构造三角定向探测组。")
    return sorted(selected), "triangular_local"


def is_visible(source, direction_deg, sensor, receive_radius=1000.0):
    delta = (sensor[0]-source[0], sensor[1]-source[1])
    if math.hypot(*delta) > receive_radius+1e-9:
        return False
    if direction_deg is None:
        return True
    angle = math.radians(direction_deg)
    return (math.cos(angle)*delta[0] + math.sin(angle)*delta[1]
            >= -1e-9)

