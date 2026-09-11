"""Continuous-position robust FIM optimization for B-Q2.

The detector position is optimized continuously inside the conservative
guaranteed-reception polygon.  Source uncertainty is represented by a
deterministic set of polygon-boundary scenarios, so the result is a numerical
near-global solution of this FIM surrogate, not a certificate for the original
continuous minimax problem.
"""

import math
import time

from common.time_model import measure_cost


_TOL = 1e-9
_FIM_SCALE = 1e12


def _polygon_centroid(vertices):
    area_twice = sum(
        first[0] * second[1] - first[1] * second[0]
        for first, second in zip(vertices, vertices[1:] + vertices[:1])
    )
    if abs(area_twice) <= _TOL:
        return (
            sum(point[0] for point in vertices) / len(vertices),
            sum(point[1] for point in vertices) / len(vertices),
        )
    cx = sum(
        (first[0] + second[0])
        * (first[0] * second[1] - first[1] * second[0])
        for first, second in zip(vertices, vertices[1:] + vertices[:1])
    ) / (3.0 * area_twice)
    cy = sum(
        (first[1] + second[1])
        * (first[0] * second[1] - first[1] * second[0])
        for first, second in zip(vertices, vertices[1:] + vertices[:1])
    ) / (3.0 * area_twice)
    return cx, cy


def _inside_convex(vertices, point, tolerance=1e-7):
    signs = []
    for first, second in zip(vertices, vertices[1:] + vertices[:1]):
        cross = ((second[0] - first[0]) * (point[1] - first[1])
                 - (second[1] - first[1]) * (point[0] - first[0]))
        if abs(cross) > tolerance:
            signs.append(cross > 0)
    return not signs or all(sign == signs[0] for sign in signs)


def _closest_on_segment(point, first, second):
    dx, dy = second[0] - first[0], second[1] - first[1]
    denominator = dx * dx + dy * dy
    if denominator <= _TOL:
        return first
    ratio = ((point[0] - first[0]) * dx
             + (point[1] - first[1]) * dy) / denominator
    ratio = max(0.0, min(1.0, ratio))
    return first[0] + ratio * dx, first[1] + ratio * dy


def project_to_polygon(point, vertices):
    """Project a point onto a closed convex polygon in Euclidean distance."""
    point = tuple(point)
    if _inside_convex(vertices, point):
        return point
    boundary = [
        _closest_on_segment(point, first, second)
        for first, second in zip(vertices, vertices[1:] + vertices[:1])
    ]
    return min(boundary, key=lambda candidate: math.dist(point, candidate))


def build_boundary_scenarios(vertices, samples_per_edge=4):
    """Build deterministic source scenarios on every edge plus the centroid."""
    if samples_per_edge < 1:
        raise ValueError("FIM每条边的场景数至少为1。")
    scenarios = []
    for first, second in zip(vertices, vertices[1:] + vertices[:1]):
        for index in range(samples_per_edge):
            ratio = index / samples_per_edge
            scenarios.append((
                first[0] + ratio * (second[0] - first[0]),
                first[1] + ratio * (second[1] - first[1]),
            ))
    scenarios.append(_polygon_centroid(vertices))
    unique = {}
    for point in scenarios:
        unique[(round(point[0], 9), round(point[1], 9))] = point
    return list(unique.values())


def bearing_fim_index(first_position, second_position, target,
                      action_time_s):
    """Return a scaled two-bearing D-optimality index per action second.

    With equal angular noise, the determinant is proportional to
    ``sin(angle)^2 / (distance_1^2 * distance_2^2)``.  The constant noise
    factor does not alter the optimizer, so it is omitted and a fixed scale is
    used solely to keep reported numbers readable.
    """
    first_vector = (target[0] - first_position[0],
                    target[1] - first_position[1])
    second_vector = (target[0] - second_position[0],
                     target[1] - second_position[1])
    first_sq = first_vector[0] ** 2 + first_vector[1] ** 2
    second_sq = second_vector[0] ** 2 + second_vector[1] ** 2
    if first_sq <= 25.0 or action_time_s <= 0.0:
        return None
    if second_sq <= 25.0:
        return _FIM_SCALE / (first_sq * 25.0 * action_time_s)
    cross = first_vector[0] * second_vector[1] - first_vector[1] * second_vector[0]
    sine_sq = cross * cross / (first_sq * second_sq)
    return _FIM_SCALE * sine_sq / (first_sq * second_sq * action_time_s)


def optimize_continuous_fim(source_region, guaranteed_region, *,
                            first_position, current_position,
                            current_channel, target_channel,
                            min_receive_radius=1000.0, seed_points=(),
                            samples_per_edge=4, initial_step_m=200.0,
                            min_step_m=2.0, max_iterations=120,
                            seed_limit=10, action_time_limits_s=(),
                            cpu_time_limit_s=None):
    """Optimize robust FIM for one or more absolute action-time limits.

    All budgets share the same deterministic scenarios and evaluation cache.
    ``cpu_time_limit_s`` is a wall-clock safety cutoff; when reached, every
    budget still returns its best feasible seed or incumbent and marks the
    overall result as timed out.
    """
    if source_region.get("status") != "bounded":
        raise ValueError("连续FIM优化需要有界源位置区域。")
    if samples_per_edge < 1 or initial_step_m <= 0 or min_step_m <= 0:
        raise ValueError("连续FIM搜索参数不合法。")
    if max_iterations < 1 or seed_limit < 1:
        raise ValueError("连续FIM迭代数和种子数至少为1。")
    if cpu_time_limit_s is not None and cpu_time_limit_s <= 0:
        raise ValueError("连续FIM CPU时间上限必须为正数。")
    limits = sorted({float(value) for value in action_time_limits_s})
    if any(not math.isfinite(value) or value < 5.0 for value in limits):
        raise ValueError("连续FIM动作时间预算必须是至少5秒的有限数。")
    if not limits:
        limits = [None]
    if guaranteed_region.get("status") != "bounded":
        return {
            "status": "unavailable",
            "method": "time_budgeted_continuous_robust_fim_pattern_search",
            "reason": "guaranteed_reception_region_empty",
            "optimality_claim": "none",
        }

    source_vertices = [tuple(point) for point in source_region["vertices"]]
    feasible_vertices = [tuple(point) for point in guaranteed_region["vertices"]]
    scenarios = [
        point for point in build_boundary_scenarios(
            source_vertices, samples_per_edge=samples_per_edge
        )
        if math.dist(first_position, point) > 5.0 + _TOL
    ]
    if not scenarios:
        return {
            "status": "unavailable",
            "method": "continuous_position_robust_fim_pattern_search",
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
        farthest = max(math.dist(point, source) for source in source_vertices)
        if farthest > min_receive_radius + 1e-6:
            return None
        timing = measure_cost(current_position, point, current_channel,
                              target_channel)
        values = [bearing_fim_index(first_position, point, target,
                                    timing.total_s)
                  for target in scenarios]
        valid = [(value, target) for value, target in zip(values, scenarios)
                 if value is not None]
        if not valid:
            return None
        robust_value, worst_target = min(valid, key=lambda item: item[0])
        result = {
            "point": point,
            "robust_fim_index_per_s": robust_value,
            "worst_case_source": worst_target,
            "action_time_s": timing.total_s,
            "time_breakdown": timing.as_dict(),
            "max_source_distance_m": farthest,
        }
        cache[key] = result
        return result

    centroid = _polygon_centroid(feasible_vertices)
    source_center = tuple(source_region["minimum_enclosing_circle"]["center"])
    raw_seeds = [centroid, source_center]
    raw_seeds.extend(tuple(point) for point in seed_points)
    raw_seeds.extend(feasible_vertices)
    raw_seeds.extend(
        ((first[0] + second[0]) / 2.0,
         (first[1] + second[1]) / 2.0)
        for first, second in zip(feasible_vertices,
                                 feasible_vertices[1:] + feasible_vertices[:1])
    )
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
            "method": "continuous_position_robust_fim_pattern_search",
            "reason": "no_feasible_seed",
            "optimality_claim": "none",
        }

    def rank_key(item):
        return (item["robust_fim_index_per_s"], -item["action_time_s"],
                -item["point"][0], -item["point"][1])

    evaluated.sort(key=rank_key, reverse=True)
    directions = [
        (math.cos(2.0 * math.pi * index / 16.0),
         math.sin(2.0 * math.pi * index / 16.0))
        for index in range(16)
    ]
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
        best_seed = max(allowed, key=rank_key)
        starts = sorted(allowed, key=rank_key, reverse=True)[:seed_limit]
        best = best_seed
        iterations_for_budget = 0
        for start in starts:
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
                candidate = max(neighbours + [current], key=rank_key)
                if (candidate["robust_fim_index_per_s"]
                        > current["robust_fim_index_per_s"] + 1e-15):
                    current = candidate
                else:
                    step /= 2.0
            if rank_key(current) > rank_key(best):
                best = current
            if timed_out:
                break
        budget_solutions.append({
            "status": "ok",
            "max_action_time_s": limit,
            "selected_point": best["point"],
            "robust_fim_index_per_s": best["robust_fim_index_per_s"],
            "worst_case_source": best["worst_case_source"],
            "action_time_s": best["action_time_s"],
            "time_breakdown": best["time_breakdown"],
            "max_source_distance_m": best["max_source_distance_m"],
            "best_seed_fim_index_per_s": best_seed[
                "robust_fim_index_per_s"
            ],
            "optimized_start_count": len(starts),
            "iteration_count": iterations_for_budget,
        })

    available = [item for item in budget_solutions if item["status"] == "ok"]
    if not available:
        return {
            "status": "unavailable",
            "method": "time_budgeted_continuous_robust_fim_pattern_search",
            "reason": "no_feasible_time_budget",
            "budget_solutions": budget_solutions,
            "timed_out": timed_out,
            "cpu_wall_time_s": time.perf_counter() - started,
            "optimality_claim": "none",
        }
    best = max(available, key=lambda item: (
        item["robust_fim_index_per_s"], -item["action_time_s"],
        -item["selected_point"][0], -item["selected_point"][1]
    ))

    return {
        "status": "ok",
        "method": "time_budgeted_continuous_robust_fim_pattern_search",
        "selected_point": best["selected_point"],
        "robust_fim_index_per_s": best["robust_fim_index_per_s"],
        "worst_case_source": best["worst_case_source"],
        "action_time_s": best["action_time_s"],
        "time_breakdown": best["time_breakdown"],
        "max_source_distance_m": best["max_source_distance_m"],
        "best_seed_fim_index_per_s": best["best_seed_fim_index_per_s"],
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
            "samples_per_edge": samples_per_edge,
            "initial_step_m": initial_step_m,
            "minimum_step_m": min_step_m,
            "max_iterations_per_start": max_iterations,
            "seed_limit": seed_limit,
            "action_time_limits_s": limits,
            "cpu_time_limit_s": cpu_time_limit_s,
        },
        "optimality_claim": "numerical_near_global_for_fim_surrogate",
    }
