"""Pure bearing geometry. No simulator ground truth or rendering dependencies.

Half-planes are normalized (a, b, c), meaning a*x + b*y <= c.
Region construction uses auditable intersection enumeration; polygon diameter
uses rotating calipers with a separate all-pairs test oracle.
"""

from itertools import combinations
from math import sin, cos, radians, hypot, dist, isfinite, sqrt

TOL = 1e-7  # metres for normalized half-planes


def bearing_planes(position, bearing_deg, error_deg=1.0):
    """Return the two normalized half-planes of one forward bearing wedge."""
    if not isfinite(float(bearing_deg)):
        raise ValueError("示向度必须是有限数值。")
    if not isfinite(float(error_deg)) or not 0 < float(error_deg) < 90:
        raise ValueError("示向度误差界须为 0 至 90 度之间的有限数值。")
    x, y = position
    low, high = radians(bearing_deg - error_deg), radians(bearing_deg + error_deg)
    normals = [(sin(low), -cos(low)), (-sin(high), cos(high))]
    return [(a, b, a*x + b*y) for a, b in normals]


def contains(planes, point):
    return all(a*point[0] + b*point[1] <= c + TOL for a, b, c in planes)


def hull(points):
    points = sorted(set(tuple(p) for p in points))
    if len(points) <= 1:
        return points

    def cross(o, a, b):
        return (a[0]-o[0])*(b[1]-o[1]) - (a[1]-o[1])*(b[0]-o[0])

    def half(seq):
        result = []
        for p in seq:
            while len(result) >= 2 and cross(result[-2], result[-1], p) <= 0:
                result.pop()
            result.append(p)
        return result

    return half(points)[:-1] + half(reversed(points))[:-1]


def _distance_squared(p, q):
    return (p[0]-q[0])**2 + (p[1]-q[1])**2


def diameter_bruteforce(vertices):
    """Independent O(n^2) oracle for a convex polygon's diameter."""
    points = list(vertices)
    if not points:
        return None, None
    if len(points) == 1:
        return 0.0, [points[0], points[0]]
    p, q = max(combinations(points, 2), key=lambda pair: _distance_squared(*pair))
    return dist(p, q), [p, q]


def diameter_calipers(vertices):
    """Convex-polygon diameter by rotating calipers: O(n).

    Input may contain duplicates, collinear points, or arbitrary ordering;
    ``hull`` first produces a strict counter-clockwise convex polygon.
    """
    points = hull(vertices)
    count = len(points)
    if count == 0:
        return None, None
    if count == 1:
        return 0.0, [points[0], points[0]]
    if count == 2:
        return dist(*points), [points[0], points[1]]

    def area2(edge_index, point_index):
        p = points[edge_index]
        q = points[(edge_index+1) % count]
        r = points[point_index % count]
        return (q[0]-p[0])*(r[1]-p[1]) - (q[1]-p[1])*(r[0]-p[0])

    opposite = 1
    best_squared = -1.0
    best_pair = None
    for edge_index in range(count):
        # The support point moves monotonically around a convex polygon.
        while area2(edge_index, opposite+1) > area2(edge_index, opposite):
            opposite = (opposite+1) % count
        candidates = [opposite]
        current = area2(edge_index, opposite)
        following = area2(edge_index, opposite+1)
        if abs(following-current) <= 1e-12*max(1.0, abs(current), abs(following)):
            candidates.append((opposite+1) % count)
        for first in (edge_index, (edge_index+1) % count):
            for second in candidates:
                value = _distance_squared(points[first], points[second])
                if value > best_squared:
                    best_squared = value
                    best_pair = sorted([points[first], points[second]])
    return sqrt(best_squared), best_pair


def diameter(vertices):
    """Production diameter implementation; see ``diameter_bruteforce`` oracle."""
    return diameter_calipers(vertices)


def minimum_enclosing_circle(vertices):
    """Small-n exact-support oracle for the minimum enclosing circle.

    A minimum circle is supported by one, two, or three boundary vertices.
    Enumerating all such supports is O(n^4), deliberately simple and auditable.
    This is supplementary to Q1's diameter-circle question and is useful for
    later guaranteed-clearance decisions.
    """
    points = hull(vertices)
    if not points:
        return None

    candidates = [((p[0], p[1]), 0.0, [p]) for p in points]
    for p, q in combinations(points, 2):
        center = ((p[0]+q[0])/2, (p[1]+q[1])/2)
        candidates.append((center, dist(center, p), [p, q]))
    for p, q, r in combinations(points, 3):
        u = (q[0]-p[0], q[1]-p[1])
        v = (r[0]-p[0], r[1]-p[1])
        determinant = 2*(u[0]*v[1]-u[1]*v[0])
        if abs(determinant) < 1e-14:
            continue
        u2 = u[0]**2 + u[1]**2
        v2 = v[0]**2 + v[1]**2
        x = (u2*v[1]-v2*u[1])/determinant
        y = (u[0]*v2-v[0]*u2)/determinant
        center = (p[0]+x, p[1]+y)
        candidates.append((center, dist(center, p), [p, q, r]))

    valid = []
    for center, radius, support in candidates:
        tolerance = max(TOL, radius*1e-10)
        if all(dist(center, point) <= radius+tolerance for point in points):
            valid.append((center, radius, support))
    if not valid:
        raise ValueError("最小包围圆数值退化，请对该定位区域进行高精度复核。")
    center, radius, support = min(valid, key=lambda item: item[1])
    return dict(center=center, radius=radius, support=support)


def intersect_halfplanes(planes):
    """Classify the actual intersection before any viewport clipping.

    Feasibility: the nearest feasible point to the origin is the origin,
    a projection on one supporting line, or a pairwise line intersection.
    Unboundedness: a nonzero recession direction is on a boundary tangent
    (or an axis when there are no effective constraints).
    Small scene baseline: O(m^3) intersection enumeration, O(n^2) diameter.
    """
    normalized = []
    for a, b, c in planes:
        length = hypot(a, b)
        if length == 0:
            if c < 0:
                return _empty()
            continue
        normalized.append((a/length, b/length, c/length))
    planes = normalized
    feasible = contains(planes, (0, 0))
    vertices = []
    for a, b, c in planes:
        feasible |= contains(planes, (a*c, b*c))
    for (a, b, c), (d, e, f) in combinations(planes, 2):
        det = a*e - b*d
        if abs(det) < 1e-14:
            continue
        p = ((c*e-b*f)/det, (a*f-c*d)/det)
        if contains(planes, p):
            vertices.append(p)
            feasible = True
    if not feasible:
        return _empty()
    directions = [(1, 0), (-1, 0), (0, 1), (0, -1)]
    for a, b, _ in planes:
        directions.extend([(b, -a), (-b, a)])
    if any(all(a*x + b*y <= 1e-13 for a, b, _ in planes)
           for x, y in directions):
        return dict(status="unbounded", vertices=[], diameter=None,
                    diameter_pair=None, diameter_circle=None,
                    minimum_enclosing_circle=None, area=None)
    vertices = hull(vertices)
    if not vertices:
        raise ValueError("边界数值退化，未能恢复有界区域顶点，请调整检测点或独立复核。")
    length, pair = diameter(vertices)
    center = [(pair[0][i]+pair[1][i])/2 for i in (0, 1)]
    farthest = max(dist(center, p) for p in vertices)
    enclosing = minimum_enclosing_circle(vertices)
    area = abs(sum(p[0]*q[1]-p[1]*q[0]
                   for p, q in zip(vertices, vertices[1:]+vertices[:1])))/2
    return dict(status="bounded", vertices=vertices, diameter=length,
                diameter_pair=pair, area=area,
                diameter_circle=dict(center=center, radius=length/2,
                                     covers=farthest <= length/2 + TOL,
                                     excess=max(0.0, farthest-length/2)),
                minimum_enclosing_circle=enclosing)


def _empty():
    return dict(status="empty", vertices=[], diameter=None,
                diameter_pair=None, diameter_circle=None,
                minimum_enclosing_circle=None, area=None)


def clip_to_box(planes, bounds):
    """For drawing ONLY: this clipped polygon is never used for diameter."""
    xmin, ymin, xmax, ymax = bounds
    polygon = [(xmin, ymin), (xmax, ymin), (xmax, ymax), (xmin, ymax)]
    for a, b, c in planes:
        output = []
        if not polygon:
            break
        for p, q in zip(polygon, polygon[1:]+polygon[:1]):
            fp, fq = a*p[0]+b*p[1]-c, a*q[0]+b*q[1]-c
            pin, qin = fp <= 0, fq <= 0
            if pin:
                output.append(p)
            if pin != qin:
                t = fp/(fp-fq)
                output.append((p[0]+t*(q[0]-p[0]), p[1]+t*(q[1]-p[1])))
        polygon = output
    return polygon


def localize(observations, bounds, error_deg=1.0):
    """Input contains detector positions and measured bearings only."""
    planes = []
    for obs in observations:
        if obs["status"] == "direction":
            planes.extend(bearing_planes(obs["position"], obs["bearing_deg"], error_deg))
    result = intersect_halfplanes(planes)
    result["bearing_count"] = len(planes)//2
    result["display_polygon"] = clip_to_box(planes, bounds) if planes else []
    result["planes"] = planes
    return result
