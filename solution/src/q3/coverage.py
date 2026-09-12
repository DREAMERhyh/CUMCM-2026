"""Coverage and finite-clear constructions used by Q3."""

import math

from common.time_model import measure_cost


def ring7():
    return [(0.0, 0.0)] + [
        (1500.0*math.cos(k*math.pi/3), 1500.0*math.sin(k*math.pi/3))
        for k in range(6)
    ]


def hub_and_ring_6(radius=1200.0):
    """原点 + 6 个半径 ``radius`` 均匀环点（候选布局 A）。"""
    return [(0.0, 0.0)] + [
        (radius*math.cos(k*math.pi/3), radius*math.sin(k*math.pi/3))
        for k in range(6)
    ]


def pure_ring_8(radius=960.0):
    """8 个半径 ``radius`` 均匀环点、无中心点（候选布局 B）。"""
    return [
        (radius*math.cos(k*math.pi/4), radius*math.sin(k*math.pi/4))
        for k in range(8)
    ]


SCAN_LAYOUTS = {
    "ring7": ring7,
    "hub_ring6": hub_and_ring_6,
    "pure_ring8": pure_ring_8,
}


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


def scan_path_length(points, start=(0.0, 0.0)):
    """从 ``start`` 出发依次访问全部停点的总路程（最后不回原点）。"""
    total = 0.0
    previous = start
    for point in points:
        total += math.dist(previous, point)
        previous = point
    return total


def scan_phase_virtual_time(points, *, start=(0.0, 0.0), start_channel=1):
    """扫描阶段虚拟时间拆分为移动/检测/切换三段（复用官方时间模型）。

    与 Q3State 扫描顺序一致：每个停点以"当前频道"开头依次测 20 个频道
    （首测不切换，其余 19 次各计 1s 切换），上一停点末尾频道即下一停点
    的首测频道，因此停点之间不产生额外切换。时间全部由 ``measure_cost``
    累计，禁止手写秒数。
    """
    movement = switching = measurement = 0.0
    position = start
    current_channel = start_channel
    for point in points:
        channel_order = [current_channel] + [
            channel for channel in range(1, 21) if channel != current_channel
        ]
        for channel in channel_order:
            timing = measure_cost(position, point, current_channel, channel)
            movement += timing.movement_s
            switching += timing.switching_s
            measurement += timing.measurement_s
            position = point
            current_channel = channel
    return {
        "movement_s": movement,
        "switching_s": switching,
        "measurement_s": measurement,
        "total_s": movement + switching + measurement,
    }


def hub_ring6_analytical_bounds(ring_radius=1200.0, *, worst_bearing_deg=30.0,
                                belt_range=(1000.0, 1800.0),
                                design_radius=995.0):
    """候选 A 的解析验证：环带 [1000,1800] 内最坏点与覆盖上界。

    中心点覆盖 ρ ≤ 995 的整圆，故环带上只需检查最近环点的距离。对
    θ=±30°（两相邻环点的 Voronoi 边界方向），d(θ,ρ)² = ρ² − 2·r·ρ·cosθ
    + r² 在 θ 固定时是 ρ 的开口向上二次函数，在闭区间 [1000,1800] 的最大
    值必在端点；而 cos 项在 θ=30° 相对两相邻环点同时取得最小，因此最坏
    点在 (θ=±30°, ρ=1800)。ρ=1000 处该点到两个相邻环点距离相等（双重
    覆盖），同为边界检查点。
    """
    theta = math.radians(worst_bearing_deg)
    def belt_distance(rho):
        return math.sqrt(rho*rho - 2.0*ring_radius*rho*math.cos(theta)
                         + ring_radius*ring_radius)
    endpoint_distances = [belt_distance(rho) for rho in belt_range]
    inner_double_cover = belt_distance(belt_range[0])
    worst_point = (belt_range[1]*math.cos(theta), belt_range[1]*math.sin(theta))
    bound = max(endpoint_distances)
    return {
        "layout": "hub_ring6",
        "ring_radius_m": ring_radius,
        "worst_point": worst_point,
        "worst_bearing_deg": worst_bearing_deg,
        "belt_range_m": list(belt_range),
        "belt_distance_formula": (
            "sqrt(rho^2 - 2*r*rho*cos(theta) + r^2) at theta=30deg"
        ),
        "belt_endpoint_distances_m": endpoint_distances,
        "max_belt_distance_m": bound,
        "inner_boundary_double_cover": {
            "theta_deg": worst_bearing_deg,
            "rho_m": belt_range[0],
            "distance_to_either_ring_point_m": inner_double_cover,
            "nearest_ring_point_count": 2,
        },
        "design_radius_m": design_radius,
        "passes_design": (
            bound <= design_radius and inner_double_cover <= design_radius
        ),
    }


def pure_ring8_analytical_bounds(ring_radius=960.0, *, worst_edge_deg=22.5,
                                 edge_rho=1800.0, design_radius=995.0):
    """候选 B 的解析验证：中心、边缘最坏点与相邻覆盖圆交点。

    中心到最近环点即环半径 r（须 ≤995）。两相邻环点夹角 45°，其 Voronoi
    边界在角平分方向 θ=22.5°，边缘最坏点取 (θ=±22.5°, ρ=1800)。相邻覆盖
    圆（半径 = design_radius）的交点位于该射线，距原点 ρ 值须 ≥1800，
    否则环带上在 ρ<1800 处会出现覆盖缝隙。
    """
    theta = math.radians(worst_edge_deg)
    center_distance = ring_radius
    edge_distance = math.sqrt(
        edge_rho*edge_rho - 2.0*ring_radius*edge_rho*math.cos(theta)
        + ring_radius*ring_radius
    )
    half_chord = ring_radius*math.sin(math.pi/8.0)
    t = math.sqrt(max(0.0, design_radius*design_radius - half_chord*half_chord))
    mid = (ring_radius*(1.0 + math.cos(math.pi/4.0))/2.0,
           ring_radius*math.sin(math.pi/4.0)/2.0)
    direction = (math.cos(theta), math.sin(theta))
    intersection = (mid[0] + t*direction[0], mid[1] + t*direction[1])
    intersection_rho = math.hypot(*intersection)
    worst_point = (edge_rho*math.cos(theta), edge_rho*math.sin(theta))
    return {
        "layout": "pure_ring8",
        "ring_radius_m": ring_radius,
        "center_distance_m": center_distance,
        "worst_point": worst_point,
        "worst_edge_bearing_deg": worst_edge_deg,
        "edge_distance_m": edge_distance,
        "adjacent_cover_intersection": {
            "bearing_deg": worst_edge_deg,
            "rho_m": intersection_rho,
            "cover_radius_m": design_radius,
        },
        "design_radius_m": design_radius,
        "passes_design": (
            center_distance <= design_radius
            and edge_distance <= design_radius
            and intersection_rho >= edge_rho - 1e-9
        ),
    }


def maximum_coverage_distance(points, *, rho_step=5.0, theta_step_deg=0.5,
                              max_rho=1800.0):
    """极坐标网格遍历 D(0,1800)，返回最大的最近停点距离及其位置。"""
    worst = -1.0
    worst_point = None
    rho_count = int(round(max_rho / rho_step)) + 1
    theta_count = int(round(360.0 / theta_step_deg))
    for index_rho in range(rho_count):
        rho = index_rho * rho_step
        for index_theta in range(theta_count):
            theta = math.radians(index_theta * theta_step_deg)
            point = (rho*math.cos(theta), rho*math.sin(theta))
            distance = nearest_coverage_distance(point, points)
            if distance > worst:
                worst = distance
                worst_point = point
    return {
        "maximum_distance_m": worst,
        "worst_point": worst_point,
        "worst_rho_m": math.hypot(*worst_point) if worst_point else None,
        "worst_bearing_deg": (math.degrees(math.atan2(
            worst_point[1], worst_point[0])) % 360.0
            if worst_point else None),
        "grid": {"rho_step_m": rho_step, "theta_step_deg": theta_step_deg,
                 "rho_count": rho_count, "theta_count": theta_count},
    }


def verify_coverage_numerically(points, *, rho_step=5.0, theta_step_deg=0.5,
                                coverage_radius=1000.0, max_rho=1800.0):
    """按规格断言数值覆盖：网格上最大最近停点距离 ≤ coverage_radius。"""
    result = maximum_coverage_distance(
        points, rho_step=rho_step, theta_step_deg=theta_step_deg,
        max_rho=max_rho,
    )
    result["coverage_radius_m"] = coverage_radius
    result["passes"] = result["maximum_distance_m"] <= coverage_radius + 1e-9
    return result

