"""MDCT v1：顺路最小绕行 refine 腿选择器（实验轮3，v2 口径）。

定格动画语义下"现实计算在虚拟时间上免费"，因此可以用实时前向预测
在候选腿位置中选最小虚拟成本（移动+测量+切换+半径折算）者：

- 候选：区域方向轴向（center-发现点）0.5/0.75/1.0 倍采样距离 R 与
  横向 ±30° 共 9 点，投影到保证接收凸多边形内（用 continuous_fim
  的 project_to_polygon）；
- 预测口径（v2 修正，P2 失败归因）：**不能用无误差名义推演**——共线
  腿在理想方向上会系统性低估深度不确定度。改用与 q2 同一口径的
  最坏后验半径 `_posterior_with_config`（对区域代表点 × ±error_deg
  端点取最大后验包围半径）作为候选腿的预测半径；
- 选择：min( move + switching + 5 + cost_per_metre * R_worst )。
本模块不动 Q2 规划器与 FIM。
"""

import math

from q2.continuous_diameter import _posterior_with_config
from q2.continuous_fim import project_to_polygon


def _candidate_directions(anchor, sampling_m=800.0):
    """以 ``anchor`` 为锚的 ±60°/±90° 横向候选（交会角 60-120° 区间）。

    v4 修正（P2 归因）：轴向/±30° 候选交会角趋近 0（锥内点与发现腿
    几乎平行）不收敛；横向 60/90° 保证有效交会。投影到保证接收域在
    调用侧完成（v5 修正）。
    """
    axis = (1.0, 0.0)  # 方向由调用方在锚与区域中心之间取；这里直接
    # 用 anchor 到区域中心的轴（见调用处）。为了不依赖外部，这里返回
    # anchor 周边 12 个方向点（60/90° 横向 × 三档 × 双侧），由调用方
    # 以"区域中心-锚"方向旋转后投影。
    points = []
    for ratio in (0.5, 0.8, 1.1):
        for angle_deg in (60.0, 90.0):
            theta = math.radians(angle_deg)
            for sign in (-1.0, 1.0):
                dx = math.cos(theta) * sign
                dy = math.sin(theta)
                points.append((anchor[0] + ratio * sampling_m * dx,
                               anchor[1] + ratio * sampling_m * dy))
    return points


def select_refine_leg(region, observations, current_position,
                      current_channel, error_deg=1.005,
                      sampling_m=800.0, cost_per_metre=0.5):
    """返回 (leg_point, worst_predicted_radius)。

    v5 修正（P2 归因，关键）：refine 腿必须落在**保证接收域**内
    （距任意可能源位置 <=1000 才能保证 direction），投影目标从"源位置
    多边形"改为 q2 的 guaranteed_reception 保守多边形；否则候选腿对
    真源多为 no_signal，region 永不收敛。全部候选按最坏后验口径评估，
    按 移动+5+切换+0.5*R_worst 取最小。
    """
    from q2.candidates import build_candidate_regions
    guaranteed = build_candidate_regions(
        region, min_receive_radius=1000.0, max_receive_radius=1500.0,
        circle_sides=72)["guaranteed_reception"]
    if guaranteed.get("status") == "bounded":
        polygon = guaranteed["vertices"]
    else:
        polygon = region["vertices"]  # 保守回退（退化情形）
    anchor = tuple(region["minimum_enclosing_circle"]["center"])
    discover = next(obs for obs in observations
                    if obs.result == "direction")
    vertices = region["vertices"]
    # v6：场景限定"核心区"（MEC 中心近邻顶点）——预测不被远端顶点主导，
    # 反映腿对真实源的收敛效率。
    core_radius = 0.0
    from common.domain import max_vertex_distance
    core_radius = max_vertex_distance(anchor, vertices)
    core = [tuple(anchor)]
    core.extend(tuple(point) for point in vertices
                if math.dist(point, anchor) <= 0.7 * core_radius)
    scenarios = core
    # 候选 = 区域中心方向 ±60°/±90° 横向 × 三档距离（交会角 60-120°）。
    axis_x = anchor[0] - discover.position[0]
    axis_y = anchor[1] - discover.position[1]
    norm = math.hypot(axis_x, axis_y)
    if norm <= 1e-9:
        axis_x, axis_y = 1.0, 0.0
        norm = 1.0
    axis = (axis_x / norm, axis_y / norm)
    lateral = (-axis[1], axis[0])
    candidates = []
    for ratio in (0.5, 0.8, 1.1):
        for angle_deg in (60.0, 90.0):
            theta = math.radians(angle_deg)
            cos_t, sin_t = math.cos(theta), math.sin(theta)
            for sign in (-1.0, 1.0):
                dx = axis[0] * cos_t + lateral[0] * sin_t * sign
                dy = axis[1] * cos_t + lateral[1] * sin_t * sign
                raw = (discover.position[0] + ratio * sampling_m * dx,
                       discover.position[1] + ratio * sampling_m * dy)
                projected = project_to_polygon(raw, polygon)
                if math.dist(projected, current_position) < 50.0:
                    continue
                candidates.append(projected)
    if not candidates:
        candidates = [project_to_polygon(anchor, polygon)]  # 保底
    best = None
    for cand in candidates:
        move = math.dist(current_position, cand)
        switching = 0.0 if current_channel == discover.channel else 1.0
        radius = 0.0
        for target in scenarios:
            for error in (-error_deg, 0.0, error_deg):
                posterior = _posterior_with_config(
                    region, cand, target, error, error_deg)
                if posterior > radius:
                    radius = posterior
        # v6 目标：先保"预测收敛腿"（radius<=19.9），再按其移动最小取；
        # 无一收敛时按 移动+5+切换+0.5*radius 折衷。
        if radius <= 19.9:
            cost = move + switching + 5.0
        else:
            cost = (move + switching + 5.0 + cost_per_metre * radius
                    + 10000.0)
        if best is None or cost < best[0]:
            best = (cost, cand, radius)
    return best[1], best[2]