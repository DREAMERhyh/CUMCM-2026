"""Directional-source coverage constructions."""

import math


def grid121():
    rows = []
    for row, y_index in enumerate(range(-5, 6)):
        xs = range(-5, 6) if row % 2 == 0 else range(5, -6, -1)
        rows.extend((500.0*x, 500.0*y_index) for x in xs)
    return [(0.0, 0.0)] + [point for point in rows if point != (0.0, 0.0)]


def four_sided_points(center, radius, rho=200.0):
    if rho/math.sqrt(2) <= radius or rho+radius > 1000.0:
        return []
    x, y = center
    return [(x+rho, y), (x, y+rho), (x-rho, y), (x, y-rho)]


def is_visible(source, direction_deg, sensor, receive_radius=1000.0):
    delta = (sensor[0]-source[0], sensor[1]-source[1])
    angle = math.radians(direction_deg)
    return (math.hypot(*delta) <= receive_radius+1e-9 and
            math.cos(angle)*delta[0] + math.sin(angle)*delta[1] >= -1e-9)

