"""Pure bearing geometry. No simulator ground truth or rendering dependencies.

Half-planes are normalized (a, b, c), meaning a*x + b*y <= c.
This deliberately uses auditable enumeration, not optimized rotating calipers.
"""

from itertools import combinations
from math import cos, sin, radians, hypot, dist

TOL = 1e-7  # metres for normalized half-planes


def bearing_planes(position, bearing_deg, error_deg=1.0):
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


def diameter(vertices):
    """A convex polygon's diameter is attained by a vertex pair: O(n^2)."""
    if not vertices:
        return None, None
    if len(vertices) == 1:
        return 0.0, [vertices[0], vertices[0]]
    p, q = max(combinations(vertices, 2), key=lambda pair: dist(*pair))
    return dist(p, q), [p, q]


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
                    diameter_pair=None, diameter_circle=None, area=None)
    vertices = hull(vertices)
    if not vertices:
        raise ValueError("边界数值退化，未能恢复有界区域顶点，请调整检测点或独立复核。")
    length, pair = diameter(vertices)
    center = [(pair[0][i]+pair[1][i])/2 for i in (0, 1)]
    farthest = max(dist(center, p) for p in vertices)
    area = abs(sum(p[0]*q[1]-p[1]*q[0]
                   for p, q in zip(vertices, vertices[1:]+vertices[:1])))/2
    return dict(status="bounded", vertices=vertices, diameter=length,
                diameter_pair=pair, area=area,
                diameter_circle=dict(center=center, radius=length/2,
                                     covers=farthest <= length/2 + TOL,
                                     excess=max(0.0, farthest-length/2)))


def _empty():
    return dict(status="empty", vertices=[], diameter=None,
                diameter_pair=None, diameter_circle=None, area=None)


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


def localize(observations, bounds):
    """Input contains detector positions and measured bearings only."""
    planes = []
    for obs in observations:
        if obs["status"] == "direction":
            planes.extend(bearing_planes(obs["position"], obs["bearing_deg"]))
    result = intersect_halfplanes(planes)
    result["bearing_count"] = len(planes)//2
    result["display_polygon"] = clip_to_box(planes, bounds) if planes else []
    result["planes"] = planes
    return result
