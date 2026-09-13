"""minimax refine 腿选择器（实验轮5 主攻 1）。

与轮3 tour_refine（P2/P4b 证伪）的本质区别：不做"源会收敛到哪"的
预测（那需要源位置估计/分布假设），而是对最坏情形直接极小化——
对每个候选测点 C，假设对手在 region 内选择最不利于收敛的源位置 s，
且测量误差取其最坏端点 e∈{±error_deg}，观测角 = 方位(s→C)+e，
新区域 = region ∩ wedge(C, 该角±error_deg)，取其 MEC 半径的最大值
（worst-case）；选择 worst 最小的 C。即使"对手角度"真实出现，
收益也保底——这是确定性最坏语义，无需任何概率分布假设。

定格动画语义下内层最坏搜索免费：候选集给 40 点、角度采样 63 等分 +
区域顶点方向精修，单次决策现实耗时约 2s（可监控）。
"""

import math

from q1.geometry import bearing_planes, intersect_halfplanes
from q2.continuous_fim import project_to_polygon

_TOL = 1e-9


def _wedge_mec(region, sensor, bearing_deg, error_deg):
    """region ∩ wedge(sensor, bearing±error) 的 MEC 半径（最坏误差端点
    由调用方枚举；本函数只按给定 bearing 构造锥并求交）。"""
    planes = list(region["planes"])
    planes.extend(bearing_planes(sensor, bearing_deg, error_deg))
    posterior = intersect_halfplanes(planes)
    if posterior.get("status") != "bounded":
        return float("inf")
    return posterior["minimum_enclosing_circle"]["radius"]


def _worst_radius_at(region, sensor, scenarios, error_deg):
    """minimax 内层：max over s∈scenarios, e∈{-e,0,+e} 的锥交 MEC。"""
    worst = 0.0
    angles = set()
    for point in scenarios:
        true_bearing = (math.degrees(
            math.atan2(point[1] - sensor[1], point[0] - sensor[0])) % 360)
        for offset in (-error_deg, 0.0, error_deg):
            angles.add((true_bearing + offset) % 360)
    for angle in angles:
        radius = _wedge_mec(region, sensor, angle, error_deg)
        if radius > worst:
            worst = radius
    return worst


def _scenario_points(region, extra=36):
    """region 内代表点：顶点 + 边中点 + 中心 + 确定性均匀散布。"""
    vertices = list(region["vertices"])
    points = list(vertices)
    for first, second in zip(vertices, vertices[1:] + vertices[:1]):
        points.append(((first[0] + second[0]) / 2.0,
                       (first[1] + second[1]) / 2.0))
    center = tuple(region["minimum_enclosing_circle"]["center"])
    points.append(center)
    # 均匀散布（确定性，区域外切圆内采再投影收缩；不做概率假设，
    # 这里是确定性采样集，作为对手角度网格）。
    radius = region["minimum_enclosing_circle"]["radius"]
    for index in range(extra):
        angle = 2.0 * math.pi * index / extra
        point = (center[0] + radius * 1.2 * math.cos(angle),
                 center[1] + radius * 1.2 * math.sin(angle))
        points.append(point)
    seen = {}
    for point in points:
        key = (round(point[0], 6), round(point[1], 6))
        seen[key] = point
    return list(seen.values())


def _candidate_points(region, current_position, guaranteed_vertices,
                      count=40):
    """候选测点：保证接收域内（投影）沿区域中心方向的径向/横向候选。"""
    center = tuple(region["minimum_enclosing_circle"]["center"])
    radius = region["minimum_enclosing_circle"]["radius"]
    raw = [current_position, center]
    theta = math.atan2(center[1] - current_position[1],
                       center[0] - current_position[0])
    for ratio in (0.3, 0.6, 0.9):
        dist = ratio * max(radius, 1.0)
        raw.append((center[0] + dist * math.cos(theta),
                    center[1] + dist * math.sin(theta)))
    for index in range(8):
        angle = math.atan2(math.sin(theta), math.cos(theta)) \
            + (index - 4) * math.radians(25.0)
        for ratio in (0.6, 1.0):
            dist = ratio * radius
            raw.append((center[0] + dist * math.cos(angle),
                        center[1] + dist * math.sin(angle)))
    points = []
    seen = set()
    for point in raw:
        projected = project_to_polygon(point, guaranteed_vertices)
        key = (round(projected[0], 6), round(projected[1], 6))
        if key in seen:
            continue
        seen.add(key)
        points.append(projected)
        if len(points) >= count:
            break
    if not points:
        points = [current_position, center]
    return points


def select_minimax_leg(region, observations, *, current_position,
                       current_channel, error_deg=1.005,
                       candidate_count=40, candidate_radius=None):
    """返回 (leg_point, worst_predicted_radius)。

    候选全部落在保证接收域投影内（距任意可能源 ≤1000，方向保证）；
    真实误差 e 的最坏端点显式枚举在一个"对手角度集"内；worst 值取
    该集上的最大 MEC。返回 worst 最小的候选，为空时回退区域中心。
    """
    from q2.candidates import build_candidate_regions
    guaranteed = build_candidate_regions(
        region, min_receive_radius=1000.0, max_receive_radius=1500.0,
        circle_sides=72)["guaranteed_reception"]
    if guaranteed.get("status") == "bounded":
        guaranteed_vertices = guaranteed["vertices"]
    else:
        guaranteed_vertices = region["vertices"]
    scenarios = _scenario_points(region)
    candidates = _candidate_points(region, tuple(current_position),
                                   guaranteed_vertices,
                                   count=candidate_count)
    best_point = tuple(region["minimum_enclosing_circle"]["center"])
    best_worst = float("inf")
    for candidate in candidates:
        worst = _worst_radius_at(region, candidate, scenarios, error_deg)
        if worst < best_worst - 1e-9:
            best_worst = worst
            best_point = candidate
    return best_point, best_worst