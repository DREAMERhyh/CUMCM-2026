"""Coverage and finite-clear constructions used by Q3."""

import math


def ring7():
    return [(0.0, 0.0)] + [
        (1500.0*math.cos(k*math.pi/3), 1500.0*math.sin(k*math.pi/3))
        for k in range(6)
    ]


def strip_clear_points(sensor, bearing_deg):
    theta = math.radians(bearing_deg)
    u = (math.cos(theta), math.sin(theta))
    n = (-u[1], u[0])
    for row, offset in enumerate((-20.0, 0.0, 20.0)):
        indices = range(76) if row % 2 == 0 else range(75, -1, -1)
        for index in indices:
            yield (sensor[0] + 20.0*index*u[0] + offset*n[0],
                   sensor[1] + 20.0*index*u[1] + offset*n[1])


def nearest_coverage_distance(point, centers):
    return min(math.dist(point, center) for center in centers)

