"""Continuous worst-case diameter optimization for B-Q2 (A2/A5 candidate).

与 ``continuous_fim`` 同接口骨架（budget_solutions / selected_point /
time_breakdown），但优化目标改为最坏情形后验包围直径：对每个候选测点，
在其可行代表点场景（剔除排除圆内点，A6 口径）与 ±error_deg 误差端点上
取后验包围半径（复用 planner ``_posterior_radius``）的最大值，作为待
最小化目标。FIM 指标不再参与选点。搜索为确定性 basin-hopping：
固定种子池（区域顶点哈希派生）+ 16 次伪随机重启 + 局地模式搜索，
anytime 预算兜底（到期返回当前最优）。

注意：planner.py 在 plan_measurement 内函数级导入本模块，因此本模块
可以顶层导入 planner 的私有评分函数而不构成循环。
"""

import math
import random
import time

from common.time_model import measure_cost

from .continuous_fim import build_boundary_scenarios, project_to_polygon

_MIN_ERR = 5.0 + 1e-9


def _deterministic_seed(vertices):
    joined = ",".join(f"{x:.6f}:{y:.6f}" for x, y in vertices)
    return abs(hash(joined)) % (2 ** 31)


def _feasible_scenarios(source_region, vertices, samples_per_edge,
                        first_position):
    """边界场景 + 排除圆内剔除（A6 口径）；全被排除时保守回退。"""
    exclusion = source_region.get("exclusion_circles") or []
    raw = build_boundary_scenarios(vertices, samples_per_edge=samples_per_edge)
    scenarios = [
        point for point in raw
        if math.dist(first_position, point) > _MIN_ERR
        and not any(math.dist(point, center) <= radius + 1e-9
                    for center, radius in exclusion)
    ]
    if not scenarios:
        scenarios = [point for point in raw
                     if math.dist(first_position, point) > _MIN_ERR]
    return scenarios


def _diameter_at(region, sensor, scenarios, error_deg):
    worst = 0.0
    worst_scenario = None
    for target in scenarios:
        for error in (-error_deg, 0.0, error_deg):
            radius = _posterior_radius(region, sensor, target, error, None)
            if radius > worst:
                worst = radius
                worst_scenario = target
    return worst, worst_scenario


def _diameter_at(region, sensor, scenarios, error_deg):
    """max over 可行代表点 x ±error_deg 端点的后验包围半径。"""
    worst = 0.0
    worst_scenario = None
    for target in scenarios:
        for error in (-error_deg, 0.0, error_deg):
            radius = _posterior_with_config(region, sensor, target, error,
                                            error_deg)
            if radius > worst:
                worst = radius
                worst_scenario = target
    return worst, worst_scenario


def _posterior_with_config(region, sensor, target, error, error_deg):
    """等效于 planner._posterior_radius 的口径（max_receive_radius=1500、
    circle_sides=24 为 Q2Config 默认值），显式传 error_deg 避免依赖 config
    对象：对候选测点模拟二次观测后的最坏后验包围半径。"""
    distance = math.dist(sensor, target)
    if distance <= 5.0:
        return min(5.0, region["minimum_enclosing_circle"]["radius"])
    from common.domain import circle_outer_planes
    from q1.geometry import bearing_planes, intersect_halfplanes

    true_bearing = math.degrees(math.atan2(target[1] - sensor[1],
                                           target[0] - sensor[0])) % 360
    planes = list(region["planes"])
    planes.extend(circle_outer_planes(sensor, 1500.0, 24))
    planes.extend(bearing_planes(sensor, true_bearing + error, error_deg))
    posterior = intersect_halfplanes(planes)
    if posterior["status"] != "bounded":
        return float("inf")
    return posterior["minimum_enclosing_circle"]["radius"]


def optimize_continuous_diameter(
    source_region, guaranteed_region, *,
    first_position, current_position, current_channel, target_channel,
    min_receive_radius=1000.0, seed_points=(),
    samples_per_edge=4, initial_step_m=200.0, min_step_m=2.0,
    max_iterations=120, seed_limit=10, restart_count=16,
    action_time_limits_s=(), cpu_time_limit_s=None, error_deg=1.005):
    """多起点 basin-hopping，最小化最坏后验直径（按动作时间预算过滤）。"""
    if source_region.get("status") != "bounded":
        raise ValueError("连续直径优化需要有界源位置区域。")
    if guaranteed_region.get("status") != "bounded":
        return {
            "status": "unavailable",
            "method": "time_budgeted_continuous_diameter_basin_hopping",
            "reason": "guaranteed_reception_region_empty",
            "optimality_claim": "none",
        }
    limits = sorted({float(value) for value in action_time_limits_s})
    if not limits:
        limits = [None]
    if any(not math.isfinite(value) or value < 5.0 for value in limits
           if value is not None):
        raise ValueError("连续直径优化动作时间预算必须至少为 5 秒。")
    vertices = [tuple(point) for point in source_region["vertices"]]
    feasible_vertices = [tuple(point) for point in
                         guaranteed_region["vertices"]]
    scenarios = _feasible_scenarios(source_region, vertices,
                                    samples_per_edge, first_position)
    if not scenarios:
        return {
            "status": "unavailable",
            "method": "continuous_diameter_pattern_search",
            "reason": "no_valid_direction_scenarios",
            "optimality_claim": "none",
        }
    cache = {}
    started = time.perf_counter()

    def out_of_time():
        return (cpu_time_limit_s is not None
                and time.perf_counter() - started >= cpu_time_limit_s)

    def evaluate(raw_point):
        point = project_to_polygon(raw_point, feasible_vertices)
        key = round(point[0], 8), round(point[1], 8)
        if key in cache:
            return cache[key]
        farthest = max(math.dist(point, source) for source in vertices)
        if farthest > min_receive_radius + 1e-6:
            return None
        timing = measure_cost(current_position, point, current_channel,
                              target_channel)
        worst, worst_scenario = _diameter_at(source_region, point,
                                             scenarios, error_deg)
        result = {
            "point": point,
            "worst_diameter_m": worst,
            "worst_case_source": worst_scenario,
            "action_time_s": timing.total_s,
            "time_breakdown": timing.as_dict(),
            "max_source_distance_m": farthest,
        }
        cache[key] = result
        return result

    centroid = (sum(p[0] for p in feasible_vertices) / len(feasible_vertices),
                sum(p[1] for p in feasible_vertices) / len(feasible_vertices))
    raw_seeds = [centroid,
                 tuple(source_region["minimum_enclosing_circle"]["center"])]
    raw_seeds.extend(tuple(point) for point in seed_points)
    raw_seeds.extend(feasible_vertices)
    rng = random.Random(_deterministic_seed(vertices))
    xs = [p[0] for p in feasible_vertices]
    ys = [p[1] for p in feasible_vertices]
    for _ in range(restart_count):
        raw_seeds.append((rng.uniform(min(xs), max(xs)),
                          rng.uniform(min(ys), max(ys))))
    evaluated = []
    seen = set()
    for seed in raw_seeds:
        result = evaluate(seed)
        if result is None:
            continue
        key = round(result["point"][0], 8), round(result["point"][1], 8)
        if key not in seen:
            seen.add(key)
            evaluated.append(result)
    if not evaluated:
        return {
            "status": "unavailable",
            "method": "continuous_diameter_pattern_search",
            "reason": "no_feasible_seed",
            "optimality_claim": "none",
        }

    def rank_key(item):
        return (item["worst_diameter_m"], item["action_time_s"],
                -item["point"][0], -item["point"][1])

    evaluated.sort(key=rank_key)
    directions = [(math.cos(2.0 * math.pi * index / 16.0),
                   math.sin(2.0 * math.pi * index / 16.0))
                  for index in range(16)]
    total_iterations = 0
    budget_solutions = []
    timed_out = False
    for limit in limits:
        allowed = [item for item in evaluated
                   if limit is None or item["action_time_s"] <= limit + 1e-9]
        if not allowed:
            budget_solutions.append({
                "status": "unavailable",
                "max_action_time_s": limit,
                "reason": "no_feasible_seed_within_time_budget",
            })
            continue
        best_seed = min(allowed, key=rank_key)
        starts = sorted(allowed, key=rank_key)[:seed_limit]
        best = best_seed
        iterations_for_budget = 0
        for start in starts:
            if out_of_time():
                timed_out = True
                break
            current = start
            step = initial_step_m
            iterations = 0
            while step >= min_step_m and iterations < max_iterations:
                if out_of_time():
                    timed_out = True
                    break
                iterations += 1
                iterations_for_budget += 1
                total_iterations += 1
                neighbours = []
                for dx, dy in directions:
                    if out_of_time():
                        timed_out = True
                        break
                    trial = evaluate((current["point"][0] + step * dx,
                                      current["point"][1] + step * dy))
                    if (trial is not None
                            and (limit is None
                                 or trial["action_time_s"] <= limit + 1e-9)):
                        neighbours.append(trial)
                candidate = min(neighbours + [current], key=rank_key)
                if (candidate["worst_diameter_m"]
                        < current["worst_diameter_m"] - 1e-12):
                    current = candidate
                else:
                    step /= 2.0
            if rank_key(current) < rank_key(best):
                best = current
            if timed_out:
                break
        budget_solutions.append({
            "status": "ok",
            "max_action_time_s": limit,
            "selected_point": best["point"],
            "worst_diameter_m": best["worst_diameter_m"],
            "worst_case_source": best["worst_case_source"],
            "action_time_s": best["action_time_s"],
            "time_breakdown": best["time_breakdown"],
            "max_source_distance_m": best["max_source_distance_m"],
            "best_seed_diameter_m": best_seed["worst_diameter_m"],
            "optimized_start_count": len(starts),
            "iteration_count": iterations_for_budget,
        })
    available = [item for item in budget_solutions if item["status"] == "ok"]
    if not available:
        return {
            "status": "unavailable",
            "method": "time_budgeted_continuous_diameter_basin_hopping",
            "reason": "no_feasible_time_budget",
            "budget_solutions": budget_solutions,
            "timed_out": timed_out,
            "cpu_wall_time_s": time.perf_counter() - started,
            "optimality_claim": "none",
        }
    best = min(available, key=lambda item: (
        item["worst_diameter_m"], item["action_time_s"],
        -item["selected_point"][0], -item["selected_point"][1]
    ))
    return {
        "status": "ok",
        "method": "time_budgeted_continuous_diameter_basin_hopping",
        "selected_point": best["selected_point"],
        "worst_diameter_m": best["worst_diameter_m"],
        "worst_case_source": best["worst_case_source"],
        "action_time_s": best["action_time_s"],
        "time_breakdown": best["time_breakdown"],
        "max_source_distance_m": best["max_source_distance_m"],
        "best_seed_diameter_m": best["best_seed_diameter_m"],
        "scenario_count": len(scenarios),
        "seed_count": len(evaluated),
        "optimized_start_count": sum(
            item.get("optimized_start_count", 0) for item in available
        ),
        "evaluation_count": len(cache),
        "iteration_count": total_iterations,
        "budget_solutions": budget_solutions,
        "timed_out": timed_out,
        "cpu_wall_time_s": time.perf_counter() - started,
        "search_parameters": {
            "objective": "worst_case_posterior_diameter",
            "samples_per_edge": samples_per_edge,
            "initial_step_m": initial_step_m,
            "minimum_step_m": min_step_m,
            "max_iterations_per_start": max_iterations,
            "seed_limit": seed_limit,
            "restart_count": restart_count,
            "action_time_limits_s": limits,
            "cpu_time_limit_s": cpu_time_limit_s,
        },
        "optimality_claim": "numerical_near_global_for_diameter_surrogate",
    }