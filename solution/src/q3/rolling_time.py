"""Finite-scenario rolling optimisation of Q3 total virtual time."""

import math
import statistics
import time

from common.domain import (build_region_from_observations,
                           max_vertex_distance, representative_points)
from common.models import BearingObservation
from common.time_model import measure_cost

from .adaptive import nearest_neighbor_order, posterior_clear_points
from .cache import (config_fingerprint, point_fingerprint,
                    posterior_fingerprint, region_fingerprint)


def _point_key(point):
    return round(point[0], 8), round(point[1], 8)


def _add_candidate(items, seen, item, source):
    if not item:
        return
    point = item.get("point", item.get("selected_point"))
    if point is None:
        return
    point = tuple(point)
    if len(point) != 2 or not all(math.isfinite(value) for value in point):
        return
    key = _point_key(point)
    if key in seen:
        return
    seen.add(key)
    items.append({"point": point, "candidate_source": source})


def extract_q2_candidate_points(plan, region, config, *, limit=12):
    """Read and deduplicate Q2 candidates without changing its public API."""
    if limit < 1:
        raise ValueError("滚动评价候选上限至少为1。")
    items, seen = [], set()
    _add_candidate(items, seen, plan.get("selected"), "top_level")
    baseline = plan.get("baseline", {})
    _add_candidate(items, seen, baseline.get("selected"), "baseline")
    continuous = plan.get("continuous_fim", {})
    if continuous.get("status") == "ok":
        _add_candidate(items, seen, continuous.get("selected"),
                       "continuous_fim")
        for item in continuous.get("candidates", []):
            _add_candidate(items, seen, item, "continuous_fim_budget")
    for item in plan.get("pareto_front", []):
        _add_candidate(items, seen, item, "pareto")

    guaranteed_q2 = [
        item for item in plan.get("candidates", [])
        if item.get("guaranteed_reception")
    ]
    guaranteed_q2.sort(key=lambda item: (
        item.get("worst_case_radius_m", float("inf")),
        item.get("action_time_s", float("inf")),
        tuple(item["point"]),
    ))
    for item in guaranteed_q2[:2]:
        _add_candidate(items, seen, item, "q2_guaranteed_sample")

    guaranteed_region = plan.get("candidate_regions", {}).get(
        "guaranteed_reception", {}
    )
    if guaranteed_region.get("status") == "bounded":
        for point in representative_points(
                guaranteed_region["vertices"], limit=5):
            _add_candidate(items, seen, {"point": point},
                           "guaranteed_region")

    vertices = region["vertices"]
    guaranteed = [
        item for item in items
        if max_vertex_distance(item["point"], vertices)
        <= config.min_receive_radius + 1e-7
    ]
    return guaranteed[:limit]


def clear_plan_cost(region, start, *, continuation_points=(), cache=None):
    """Return grid-route cost plus a one-step multi-source continuation."""
    continuation_points = tuple(tuple(point) for point in continuation_points)

    def compute():
        points = posterior_clear_points(region)
        ordered = nearest_neighbor_order(points, start)
        current = tuple(start)
        distance_m = 0.0
        for point in ordered:
            distance_m += math.dist(current, point)
            current = point
        base_cost_s = (
            distance_m / 5.0 + 3.0 * len(ordered)
            + (2.0 if ordered else 0.0)
        )
        continuation_s = (
            min(math.dist(current, point)
                for point in continuation_points) / 5.0
            if continuation_points else 0.0
        )
        return {
            "cost_s": base_cost_s + continuation_s,
            "base_clear_cost_s": base_cost_s,
            "continuation_cost_s": continuation_s,
            "point_count": len(points),
            "route_end": current,
        }

    if cache is None:
        return compute()
    key = (
        region_fingerprint(region), point_fingerprint(start),
        tuple(point_fingerprint(point) for point in continuation_points),
    )
    return cache.get_or_compute("clear_route", key, compute, clone=True)


def risk_summary(values, *, cvar_alpha=0.9):
    """Uniform finite-scenario summary; it is not a probability claim."""
    if not values:
        raise ValueError("风险汇总至少需要一个完整场景。")
    if not 0.0 < cvar_alpha < 1.0:
        raise ValueError("CVaR分位必须位于(0,1)。")
    ordered = sorted(float(value) for value in values)
    p90_index = max(0, math.ceil(0.9 * len(ordered)) - 1)
    cvar_index = max(0, math.ceil(cvar_alpha * len(ordered)) - 1)
    return {
        "mean_s": statistics.fmean(ordered),
        "p90_s": ordered[p90_index],
        "cvar_s": statistics.fmean(ordered[cvar_index:]),
        "worst_s": ordered[-1],
    }


def _posterior_branch(track, point, target, error_deg, config,
                      continuation_points=(), cache=None):
    distance = math.dist(point, target)
    if distance <= 5.0:
        continuation_s = (
            min(math.dist(point, other) for other in continuation_points) / 5.0
            if continuation_points else 0.0
        )
        return {"clear_cost_s": 5.0 + continuation_s,
                "clear_point_count": 1,
                "branch": "near"}
    true_bearing = math.degrees(math.atan2(
        target[1] - point[1], target[0] - point[0]
    )) % 360.0
    reported = (true_bearing + error_deg) % 360.0
    observation = BearingObservation(
        point, track.channel, "direction", reported
    )
    posterior = build_region_from_observations(
        [*track.observations, observation],
        error_deg=config.error_deg,
        arena_radius=config.arena_radius,
        max_receive_radius=config.max_receive_radius,
        circle_sides=config.circle_sides,
        q2_version=config.q2_version,
    )
    if posterior.get("status") != "bounded":
        raise RuntimeError("测后有限场景没有产生有界后验。")
    clear = clear_plan_cost(
        posterior, point, continuation_points=continuation_points,
        cache=cache,
    )
    return {
        "clear_cost_s": clear["cost_s"],
        "clear_point_count": clear["point_count"],
        "branch": "direction",
    }


def evaluate_candidate(track, point, *, current_position, current_channel,
                       config, scenario_limit=4, cvar_alpha=0.9,
                       deadline=None, continuation_points=(), cache=None):
    """Evaluate one guaranteed point using real posterior clear covers."""
    point = tuple(point)
    continuation_points = tuple(tuple(item) for item in continuation_points)

    def compute():
        timing = measure_cost(
            current_position, point, current_channel, track.channel
        )
        if scenario_limit == 1:
            targets = [tuple(
                track.region["minimum_enclosing_circle"]["center"]
            )]
        else:
            targets = representative_points(
                track.region["vertices"], limit=scenario_limit
            )
        clear_costs, point_counts = [], []
        for target in targets:
            errors = (0.0,) if math.dist(point, target) <= 5.0 else (
                -config.error_deg, 0.0, config.error_deg,
            )
            for error in errors:
                if deadline is not None and time.perf_counter() >= deadline:
                    return None
                branch = _posterior_branch(
                    track, point, target, error, config,
                    continuation_points=continuation_points, cache=cache,
                )
                clear_costs.append(branch["clear_cost_s"])
                point_counts.append(branch["clear_point_count"])
        risk = risk_summary(clear_costs, cvar_alpha=cvar_alpha)
        return {
            "point": point,
            "measure_action_time_s": timing.total_s,
            "measure_time_breakdown": timing.as_dict(),
            "post_clear_mean_s": risk["mean_s"],
            "post_clear_p90_s": risk["p90_s"],
            "post_clear_cvar_s": risk["cvar_s"],
            "post_clear_worst_s": risk["worst_s"],
            "mean_clear_point_count": statistics.fmean(point_counts),
            "scenario_count": len(clear_costs),
        }

    if cache is None:
        return compute()
    key = (
        posterior_fingerprint(track), point_fingerprint(point),
        point_fingerprint(current_position), current_channel,
        config_fingerprint(config), scenario_limit, cvar_alpha,
        tuple(point_fingerprint(item) for item in continuation_points),
    )
    return cache.get_or_compute(
        "candidate_scenario", key, compute, clone=True,
        cache_if=lambda value: value is not None,
    )


def _clear_decision(clear_now_s, *, status, timed_out, reason,
                    evaluated_candidate_count=0, cpu_wall_time_s=0.0):
    return {
        "decision": "clear",
        "selected_point": None,
        "candidate_source": "clear_now",
        "clear_now_cost_s": clear_now_s,
        "measure_action_time_s": 0.0,
        "post_clear_mean_s": clear_now_s,
        "post_clear_p90_s": clear_now_s,
        "post_clear_cvar_s": clear_now_s,
        "post_clear_worst_s": clear_now_s,
        "estimated_total_cost_s": clear_now_s,
        "estimated_saving_s": 0.0,
        "guaranteed_reception": True,
        "scenario_count": 0,
        "solver_status": status,
        "timed_out": timed_out,
        "reason": reason,
        "evaluated_candidate_count": evaluated_candidate_count,
        "cpu_wall_time_s": cpu_wall_time_s,
    }


def evaluate_total_time_decision(
        track, plan, *, current_position, current_channel, config,
        savings_margin_s=10.0, scenario_limit=4, candidate_limit=12,
        cvar_alpha=0.9, risk_metric="p90", cpu_time_limit_s=1.0,
        continuation_points=(), cache=None):
    """Compare immediate clearing with one measurement and replanning.

    The result is a finite-scenario numerical approximation.  Only candidates
    that guarantee reception for every point in the current convex posterior
    are considered, so no unmodelled ``no_signal`` branch is hidden.
    """
    if risk_metric not in ("p90", "cvar", "worst", "mean"):
        raise ValueError("滚动风险指标必须为p90、cvar、worst或mean。")
    if savings_margin_s < 0.0 or cpu_time_limit_s <= 0.0:
        raise ValueError("滚动节省余量不能为负，CPU时限必须为正。")
    started = time.perf_counter()
    deadline = started + cpu_time_limit_s
    continuation_points = tuple(continuation_points)
    clear_now = clear_plan_cost(
        track.region, current_position,
        continuation_points=continuation_points,
        cache=cache,
    )["cost_s"]
    candidates = extract_q2_candidate_points(
        plan, track.region, config, limit=candidate_limit
    )
    if not candidates:
        return _clear_decision(
            clear_now, status="fallback", timed_out=False,
            reason="no_guaranteed_candidate",
            cpu_wall_time_s=time.perf_counter() - started,
        )

    evaluated = []
    timed_out = False
    for item in candidates:
        if time.perf_counter() >= deadline:
            timed_out = True
            break
        timing = measure_cost(
            current_position, item["point"], current_channel, track.channel
        )
        if timing.total_s + 5.0 + savings_margin_s >= clear_now:
            continue
        result = evaluate_candidate(
            track, item["point"],
            current_position=current_position,
            current_channel=current_channel,
            config=config,
            scenario_limit=scenario_limit,
            cvar_alpha=cvar_alpha,
            deadline=deadline,
            continuation_points=continuation_points,
            cache=cache,
        )
        if result is None:
            timed_out = True
            break
        result["candidate_source"] = item["candidate_source"]
        result["risk_cost_s"] = result[f"post_clear_{risk_metric}_s"]
        result["estimated_total_cost_s"] = (
            result["measure_action_time_s"] + result["risk_cost_s"]
        )
        result["estimated_saving_s"] = (
            clear_now - result["estimated_total_cost_s"]
        )
        evaluated.append(result)

    elapsed = time.perf_counter() - started
    if not evaluated:
        return _clear_decision(
            clear_now,
            status="fallback" if timed_out else "ok",
            timed_out=timed_out,
            reason=("time_limit_before_complete_candidate" if timed_out
                    else "no_candidate_can_beat_clear_lower_bound"),
            cpu_wall_time_s=elapsed,
        )
    best = min(evaluated, key=lambda item: (
        item["estimated_total_cost_s"],
        item["measure_action_time_s"] + item["post_clear_mean_s"],
        item["measure_action_time_s"] + item["post_clear_worst_s"],
        item["mean_clear_point_count"],
        item["measure_action_time_s"], item["candidate_source"],
        item["point"],
    ))
    worthwhile = best["estimated_total_cost_s"] + savings_margin_s < clear_now
    status = "partial" if timed_out else "ok"
    if not worthwhile:
        decision = _clear_decision(
            clear_now, status=status, timed_out=timed_out,
            reason="risk_adjusted_total_not_better",
            evaluated_candidate_count=len(evaluated),
            cpu_wall_time_s=elapsed,
        )
        decision["best_rejected_candidate"] = best
        return decision
    return {
        "decision": "measure",
        "selected_point": best["point"],
        "candidate_source": best["candidate_source"],
        "clear_now_cost_s": clear_now,
        "measure_action_time_s": best["measure_action_time_s"],
        "measure_time_breakdown": best["measure_time_breakdown"],
        "post_clear_mean_s": best["post_clear_mean_s"],
        "post_clear_p90_s": best["post_clear_p90_s"],
        "post_clear_cvar_s": best["post_clear_cvar_s"],
        "post_clear_worst_s": best["post_clear_worst_s"],
        "estimated_total_cost_s": best["estimated_total_cost_s"],
        "estimated_saving_s": best["estimated_saving_s"],
        "guaranteed_reception": True,
        "scenario_count": best["scenario_count"],
        "solver_status": status,
        "timed_out": timed_out,
        "reason": "risk_adjusted_total_saving",
        "risk_metric": risk_metric,
        "evaluated_candidate_count": len(evaluated),
        "cpu_wall_time_s": elapsed,
    }
