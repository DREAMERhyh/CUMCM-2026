"""Deterministic finite candidate construction for B-Q2."""

import math


def generate_candidates(region, current_position, first_bearing_deg,
                        *, forward_steps=(100.0, 250.0, 500.0, 750.0),
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
    unique = {}
    for point in raw:
        if all(math.isfinite(v) and abs(v) <= 2_000_000 for v in point):
            unique[(round(point[0], 9), round(point[1], 9))] = point
    return list(unique.values())
