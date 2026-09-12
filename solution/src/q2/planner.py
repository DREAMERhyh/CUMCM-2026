"""Auditable set-based second-measurement planner for B-Q2."""

from dataclasses import asdict, dataclass
import math
import time

from common.domain import (build_region_from_observations,
                           extend_region_with_observation,
                           max_vertex_distance, representative_points)
from common.models import BearingObservation
from common.time_model import measure_cost
from .candidates import build_candidate_regions, generate_candidates
from .continuous_fim import optimize_continuous_fim
from .near_optimal import build_near_optimal_regions, local_sample_points


@dataclass(frozen=True)
class Q2Config:
    error_deg: float = 1.005
    arena_radius: float = 1800.0
    min_receive_radius: float = 1000.0
    max_receive_radius: float = 1500.0
    circle_sides: int = 24
    candidate_region_sides: int = 72
    scenario_limit: int = 8
    uncertainty_seconds_per_metre: float = 0.5
    continuous_fim_enabled: bool = True
    fim_samples_per_edge: int = 4
    fim_initial_step_m: float = 200.0
    fim_min_step_m: float = 2.0
    fim_max_iterations: int = 120
    fim_seed_limit: int = 10
    fim_extra_time_budgets_s: tuple = (15.0, 30.0, 60.0)
    fim_execution_extra_time_s: float = 30.0
    fim_cpu_time_limit_s: float = 8.0
    near_optimal_region_mode: str = "online"
    near_optimal_region_cpu_limit_s: float = 5.0
    near_optimal_time_slack_s: float = 10.0
    near_optimal_tolerances: tuple = (0.05, 0.10)


def _posterior_radius(region, observations, sensor, target, error, config):
    distance = math.dist(sensor, target)
    if distance <= 5.0:
        return min(5.0, region["minimum_enclosing_circle"]["radius"])
    true_bearing = math.degrees(math.atan2(target[1]-sensor[1],
                                           target[0]-sensor[0])) % 360
    observation = BearingObservation(
        sensor, observations[-1].channel, "direction", true_bearing+error
    )
    posterior = extend_region_with_observation(
        region, observation, error_deg=config.error_deg,
        max_receive_radius=config.max_receive_radius,
        circle_sides=config.circle_sides,
    )
    if posterior["status"] != "bounded":
        return float("inf")
    return posterior["minimum_enclosing_circle"]["radius"]


def _fim_proxy(sensor, current_position, nominal_target, action_seconds):
    a = (nominal_target[0]-current_position[0],
         nominal_target[1]-current_position[1])
    b = (nominal_target[0]-sensor[0], nominal_target[1]-sensor[1])
    da, db = math.hypot(*a), math.hypot(*b)
    if da <= 5 or db <= 5:
        return 0.0
    sine = abs(a[0]*b[1]-a[1]*b[0])/(da*db)
    return sine/(da*db*action_seconds)


def score_candidates(region, observations, candidates, current_position,
                     current_channel, target_channel, config=Q2Config()):
    vertices = region["vertices"]
    scenarios = representative_points(vertices, config.scenario_limit)
    current_radius = region["minimum_enclosing_circle"]["radius"]
    nominal = tuple(region["minimum_enclosing_circle"]["center"])
    scores = []
    for sensor in candidates:
        timing = measure_cost(current_position, sensor, current_channel,
                              target_channel)
        guaranteed = max_vertex_distance(sensor, vertices) <= config.min_receive_radius + 1e-7
        radii = []
        for target in scenarios:
            distance = math.dist(sensor, target)
            if distance > config.max_receive_radius:
                radii.append(current_radius)
                continue
            for error in (-config.error_deg, 0.0, config.error_deg):
                radii.append(_posterior_radius(
                    region, observations, sensor, target, error, config
                ))
            if distance > config.min_receive_radius:
                radii.append(current_radius)  # unknown R may produce no_signal
        if not guaranteed:
            radii.append(current_radius)
        worst_radius = max(radii, default=current_radius)
        score = timing.total_s + config.uncertainty_seconds_per_metre*worst_radius
        scores.append({
            "point": tuple(sensor),
            "guaranteed_reception": guaranteed,
            "worst_case_radius_m": worst_radius,
            "action_time_s": timing.total_s,
            "time_breakdown": timing.as_dict(),
            "score": score,
            "fim_proxy_per_s": _fim_proxy(sensor, observations[0].position,
                                             nominal, timing.total_s),
        })
    return scores


def _pareto_front(items):
    """Return points not dominated in both action time and posterior radius."""
    ordered = sorted(items, key=lambda item: (
        item["action_time_s"], item["worst_case_radius_m"], item["point"]
    ))
    front = []
    best_radius = float("inf")
    for item in ordered:
        if item["worst_case_radius_m"] < best_radius - 1e-9:
            front.append(item)
            best_radius = item["worst_case_radius_m"]
    return front


def _near_optimal_outputs(region, observations, candidate_region, branches,
                          current_position, current_channel, target_channel,
                          first, config):
    mode = config.near_optimal_region_mode
    if mode == "off" or candidate_region.get("status") != "bounded":
        status = "disabled" if mode == "off" else "unavailable"
        for branch in branches:
            branch["near_optimal_regions"] = {}
            branch["near_optimal_region_meta"] = {
                "status": status,
                "mode": mode,
                "reason": ("disabled_by_config" if mode == "off"
                           else "guaranteed_reception_region_empty"),
            }
        return {"status": status, "evaluated_point_count": 0,
                "cpu_wall_time_s": 0.0}

    started = time.perf_counter()
    deadline = started + config.near_optimal_region_cpu_limit_s
    feasible_vertices = candidate_region["vertices"]
    points_by_branch = {
        branch["method"]: local_sample_points(
            branch["selected_point"], feasible_vertices, mode=mode
        )
        for branch in branches
    }
    cache = {}
    timed_out = False
    max_length = max(len(points) for points in points_by_branch.values())
    for index in range(max_length):
        for points in points_by_branch.values():
            if index >= len(points):
                continue
            if time.perf_counter() >= deadline:
                timed_out = True
                break
            point = points[index]
            key = round(point[0], 8), round(point[1], 8)
            if key not in cache:
                cache[key] = score_candidates(
                    region, observations, [point], current_position,
                    current_channel, target_channel, config,
                )[0]
        if timed_out:
            break

    for branch in branches:
        reference = branch["selected"]
        key = round(reference["point"][0], 8), round(reference["point"][1], 8)
        cache[key] = reference
        samples = [cache[(round(point[0], 8), round(point[1], 8))]
                   for point in points_by_branch[branch["method"]]
                   if (round(point[0], 8), round(point[1], 8)) in cache]
        result = build_near_optimal_regions(
            reference, samples,
            first_position=first.position,
            first_bearing_deg=first.bearing_deg,
            tolerances=config.near_optimal_tolerances,
            time_slack_s=config.near_optimal_time_slack_s,
            mode=mode, timed_out=timed_out,
        )
        branch["near_optimal_regions"] = result.pop("regions")
        branch["near_optimal_region_meta"] = result
    return {
        "status": "partial" if timed_out else "ok",
        "evaluated_point_count": len(cache),
        "cpu_wall_time_s": time.perf_counter() - started,
        "timed_out": timed_out,
    }


def plan_measurement(region, observations, *, current_position=None,
                     current_channel=None, target_channel=None,
                     config=Q2Config()):
    planning_started = time.perf_counter()
    observations = list(observations)
    directions = [obs for obs in observations if obs.result == "direction"]
    if not directions:
        raise ValueError("测点规划至少需要一次 direction 观测。")
    first = directions[0]
    current_position = tuple(current_position or observations[-1].position)
    target_channel = target_channel or first.channel
    current_channel = current_channel or target_channel
    candidate_regions = build_candidate_regions(
        region,
        min_receive_radius=config.min_receive_radius,
        max_receive_radius=config.max_receive_radius,
        circle_sides=config.candidate_region_sides,
    )
    candidates = generate_candidates(
        region, current_position, first.bearing_deg,
        guaranteed_region=candidate_regions["guaranteed_reception"],
    )
    scores = score_candidates(region, observations, candidates,
                              current_position, current_channel,
                              target_channel, config)
    scores = sorted(scores, key=lambda item: (item["score"],
                                               -item["fim_proxy_per_s"],
                                               item["point"]))
    for index, item in enumerate(scores, 1):
        item["candidate_id"] = f"C{index:02d}"
    guaranteed = [item for item in scores if item["guaranteed_reception"]]
    pool = guaranteed or scores
    selected = min(pool, key=lambda item: (item["score"],
                                           -item["fim_proxy_per_s"],
                                           item["point"]))
    fim_choice = max(scores, key=lambda item: (item["fim_proxy_per_s"],
                                               -item["score"]))
    baseline = {
        "method": "discrete_set_score",
        "selected_point": selected["point"],
        "selected": selected,
        "candidate_count": len(scores),
        "guaranteed_candidate_count": len(guaranteed),
    }
    if config.continuous_fim_enabled:
        action_time_limits = [
            selected["action_time_s"] + extra
            for extra in config.fim_extra_time_budgets_s
        ]
        continuous_fim = optimize_continuous_fim(
            region,
            candidate_regions["guaranteed_reception"],
            first_position=first.position,
            current_position=current_position,
            current_channel=current_channel,
            target_channel=target_channel,
            min_receive_radius=config.min_receive_radius,
            seed_points=[item["point"] for item in (guaranteed or scores)],
            samples_per_edge=config.fim_samples_per_edge,
            initial_step_m=config.fim_initial_step_m,
            min_step_m=config.fim_min_step_m,
            max_iterations=config.fim_max_iterations,
            seed_limit=config.fim_seed_limit,
            action_time_limits_s=action_time_limits,
            cpu_time_limit_s=config.fim_cpu_time_limit_s,
        )
        if continuous_fim["status"] == "ok":
            solutions = [item for item in continuous_fim["budget_solutions"]
                         if item["status"] == "ok"]
            unique_points = {}
            for item in solutions:
                point = tuple(item["selected_point"])
                unique_points[(round(point[0], 8), round(point[1], 8))] = point
            rescored = score_candidates(
                region, observations, list(unique_points.values()),
                current_position, current_channel, target_channel, config,
            )
            by_point = {(round(item["point"][0], 8),
                         round(item["point"][1], 8)): item
                        for item in rescored}
            fim_candidates = []
            for index, solution in enumerate(solutions, 1):
                key = (round(solution["selected_point"][0], 8),
                       round(solution["selected_point"][1], 8))
                comparable = dict(by_point[key])
                comparable["candidate_id"] = f"FIM-T{index:02d}"
                comparable["max_action_time_s"] = solution[
                    "max_action_time_s"
                ]
                comparable["robust_fim_index_per_s"] = solution[
                    "robust_fim_index_per_s"
                ]
                fim_candidates.append(comparable)
                solution["set_evaluation"] = comparable
            execution_limit = (selected["action_time_s"]
                               + config.fim_execution_extra_time_s)
            executable = [item for item in fim_candidates
                          if item["action_time_s"] <= execution_limit + 1e-9]
            executable = executable or fim_candidates
            comparable = min(executable, key=lambda item: (
                item["worst_case_radius_m"], item["action_time_s"],
                -item["robust_fim_index_per_s"], item["point"]
            ))
            continuous_fim["fim_surrogate_best_point"] = continuous_fim[
                "selected_point"
            ]
            continuous_fim["fim_surrogate_best_index_per_s"] = (
                continuous_fim["robust_fim_index_per_s"]
            )
            continuous_fim["selected_point"] = comparable["point"]
            continuous_fim["robust_fim_index_per_s"] = comparable[
                "robust_fim_index_per_s"
            ]
            selected_solution = min(
                solutions,
                key=lambda item: abs(item["max_action_time_s"]
                                     - comparable["max_action_time_s"]),
            )
            continuous_fim["best_seed_fim_index_per_s"] = selected_solution[
                "best_seed_fim_index_per_s"
            ]
            continuous_fim["selected"] = comparable
            continuous_fim["selected_score"] = comparable["score"]
            continuous_fim["score_delta_vs_baseline"] = (
                comparable["score"] - selected["score"]
            )
            continuous_fim["radius_delta_vs_baseline_m"] = (
                comparable["worst_case_radius_m"]
                - selected["worst_case_radius_m"]
            )
            continuous_fim["execution_action_time_limit_s"] = execution_limit
            continuous_fim["candidates"] = fim_candidates
    else:
        continuous_fim = {
            "status": "disabled",
            "method": "continuous_position_robust_fim_pattern_search",
            "reason": "disabled_by_config",
            "optimality_claim": "none",
        }
    choice_items = [{**selected, "source": "baseline"}]
    if continuous_fim.get("status") == "ok":
        choice_items.extend({**item, "source": "continuous_fim"}
                            for item in continuous_fim["candidates"])
    pareto_front = _pareto_front(choice_items)
    final_pool = [choice_items[0]]
    if continuous_fim.get("status") == "ok":
        final_pool.append({**continuous_fim["selected"],
                           "source": "continuous_fim"})
    recommended = min(final_pool, key=lambda item: (
        item["worst_case_radius_m"], item["action_time_s"], item["point"]
    ))
    branches_for_regions = [baseline]
    if continuous_fim.get("status") == "ok":
        branches_for_regions.append(continuous_fim)
    near_optimal_summary = _near_optimal_outputs(
        region, observations,
        candidate_regions["guaranteed_reception"], branches_for_regions,
        current_position, current_channel, target_channel, first, config,
    )
    comparison = {
        "score_definition": (
            "action_time_s + uncertainty_seconds_per_metre "
            "* worst_case_radius_m"
        ),
        "lower_is_better": True,
        "baseline_score": selected["score"],
        "continuous_fim_score": continuous_fim.get("selected_score"),
        "continuous_minus_baseline": continuous_fim.get(
            "score_delta_vs_baseline"
        ),
        "baseline_worst_case_radius_m": selected["worst_case_radius_m"],
        "continuous_fim_worst_case_radius_m": (
            continuous_fim.get("selected", {}).get("worst_case_radius_m")
        ),
        "continuous_minus_baseline_radius_m": continuous_fim.get(
            "radius_delta_vs_baseline_m"
        ),
    }
    return {
        "method": "time_budgeted_fim_pareto_hybrid",
        "selected_point": recommended["point"],
        "selected": recommended,
        "recommendation_source": recommended["source"],
        "baseline": baseline,
        "continuous_fim": continuous_fim,
        "pareto_front": pareto_front,
        "comparison": comparison,
        "fim_baseline_point": fim_choice["point"],
        "candidate_count": len(scores),
        "guaranteed_candidate_count": len(guaranteed),
        "candidates": scores,
        "candidate_regions": candidate_regions,
        "region": region,
        "config": asdict(config),
        "near_optimal_region_summary": near_optimal_summary,
        "planning_cpu_wall_time_s": time.perf_counter() - planning_started,
        "limitations": [
            "源位置圆域先作整圆粗外切，再以解析端点切线和顶点超差切线保守细化。",
            "保证接收域是圆交集的内近似；可能接收域是圆盘Minkowski和的外近似。",
            "最坏情形在有限边界场景和误差端点上计算，不声称连续全局最优。",
            "连续FIM在测点坐标上优化，但源位置鲁棒性仍由有限边界场景近似。",
            "连续FIM优化的是信息量替代目标；最终另用离散基线的集合评分同口径比较。",
            "5%/10%近优域是已验证局部采样点凸包的绘图近似，不是连续置信区域或严格子水平集证书。",
        ],
    }


def plan_second_point(first_observation, *, current_channel=None,
                      config=Q2Config()):
    if first_observation.result != "direction":
        raise ValueError("Q2需要第一检测点返回 direction。")
    region = build_region_from_observations(
        [first_observation], error_deg=config.error_deg,
        arena_radius=config.arena_radius,
        max_receive_radius=config.max_receive_radius,
        circle_sides=config.circle_sides,
    )
    return plan_measurement(
        region, [first_observation],
        current_position=first_observation.position,
        current_channel=current_channel or first_observation.channel,
        target_channel=first_observation.channel,
        config=config,
    )
