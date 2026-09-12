"""Finite-scenario cost gates for direction-aware Q4 measurements.

These helpers only rank actions.  Continuous completeness remains guaranteed
by the certified probe sets and the 27 m posterior clear cover.
"""

import math
import time

from common.domain import build_region_from_observations
from common.models import BearingObservation
from common.time_model import measure_cost
from q3.adaptive import nearest_neighbor_order, posterior_clear_points
from q3.joint import predicted_clear_cost

from .directional import is_visible


def _point_key(point):
    return round(point[0], 8), round(point[1], 8)


def _route_cost(points, start, continuation_points=()):
    ordered = nearest_neighbor_order(points, start)
    current = tuple(start)
    distance_m = 0.0
    for point in ordered:
        distance_m += math.dist(current, point)
        current = point
    base = distance_m/5.0 + 3.0*len(ordered) + (2.0 if ordered else 0.0)
    continuation = (
        min(math.dist(current, point) for point in continuation_points)/5.0
        if continuation_points else 0.0
    )
    return base+continuation, base, current


def _sample_scenarios(scenarios, limit):
    """Deterministic weighted-quantile sample with equal retained mass."""
    scenarios = sorted(scenarios, key=lambda item: (
        item.position, item.receive_radius,
        -1.0 if item.direction_deg is None else item.direction_deg,
    ))
    if len(scenarios) <= limit:
        return [(item, item.weight) for item in scenarios]
    cumulative = []
    total = 0.0
    for item in scenarios:
        total += item.weight
        cumulative.append(total)
    selected = {}
    index = 0
    for sample_index in range(limit):
        target = total*(sample_index+0.5)/limit
        while index+1 < len(cumulative) and cumulative[index] < target:
            index += 1
        selected[scenarios[index]] = selected.get(scenarios[index], 0.0)+1.0/limit
    return list(selected.items())


def _weighted_risk(values, metric, alpha):
    if not values:
        raise ValueError("Q4风险汇总至少需要一个场景。")
    total_weight = sum(weight for _, weight in values)
    if total_weight <= 0.0:
        raise ValueError("Q4场景权重必须为正数。")
    normalized = sorted(
        ((float(value), weight/total_weight) for value, weight in values),
        key=lambda item: item[0],
    )
    mean = sum(value*weight for value, weight in normalized)

    def quantile(level):
        cumulative = 0.0
        for value, weight in normalized:
            cumulative += weight
            if cumulative >= level-1e-12:
                return value
        return normalized[-1][0]

    threshold = quantile(alpha)
    remaining = 1.0-alpha
    tail_sum = 0.0
    for value, weight in reversed(normalized):
        take = min(weight, remaining)
        tail_sum += value*take
        remaining -= take
        if remaining <= 1e-12:
            break
    summary = {
        "mean": mean,
        "p90": quantile(0.9),
        "cvar": tail_sum/max(1e-12, 1.0-alpha),
        "worst": normalized[-1][0],
    }
    return summary[metric], summary


def _probe_order(points, weighted_scenarios, *, current_position,
                 current_channel, target_channel, forced_first=None):
    remaining = list(dict.fromkeys(tuple(point) for point in points))
    active = list(weighted_scenarios)
    ordered = []
    current = tuple(current_position)
    channel = current_channel
    while remaining:
        if forced_first is not None and not ordered:
            point = tuple(forced_first)
        else:
            def key(candidate):
                visible_weight = sum(
                    weight for scenario, weight in active
                    if is_visible(
                        scenario.position, scenario.direction_deg, candidate,
                        scenario.receive_radius,
                    )
                )
                timing = measure_cost(
                    current, candidate, channel, target_channel,
                ).total_s
                return (-visible_weight, timing, candidate)
            point = min(remaining, key=key)
        remaining.remove(point)
        ordered.append(point)
        active = [
            (scenario, weight) for scenario, weight in active
            if not is_visible(
                scenario.position, scenario.direction_deg, point,
                scenario.receive_radius,
            )
        ]
        current = point
        channel = target_channel
    return ordered


def _posterior_after_direction(track, point, target, error, config):
    true_bearing = math.degrees(math.atan2(
        target[1]-point[1], target[0]-point[0],
    )) % 360.0
    observation = BearingObservation(
        tuple(point), track.channel, "direction", (true_bearing+error) % 360.0,
    )
    return build_region_from_observations(
        [*track.observations, observation],
        error_deg=config.error_deg,
        arena_radius=config.arena_radius,
        max_receive_radius=config.max_receive_radius,
        circle_sides=config.circle_sides,
        q2_version=config.q2_version,
    )


def _clear_decision(clear_now_s, *, reason, status="ok", timed_out=False,
                    evaluated_sequence_count=0, elapsed_s=0.0):
    return {
        "decision": "clear",
        "selected_point": None,
        "clear_now_cost_s": clear_now_s,
        "estimated_total_cost_s": clear_now_s,
        "estimated_saving_s": 0.0,
        "reason": reason,
        "solver_status": status,
        "timed_out": timed_out,
        "evaluated_sequence_count": evaluated_sequence_count,
        "cpu_wall_time_s": elapsed_s,
    }


def evaluate_directional_probe_decision(
        track, belief, probe_points, *, current_position, current_channel,
        config, continuation_points=(), remaining_clear_points=None,
        savings_margin_s=10.0, risk_metric="cvar", cvar_alpha=0.9,
        scenario_limit=48, candidate_limit=8, cpu_time_limit_s=1.0,
        one_step_replan=False):
    """Compare immediate clearing with one certified sequential probe group.

    In bundle mode, each scenario walks through the proposed point order until
    its first visible result.  ``one_step_replan`` instead evaluates only the
    next measurement and uses the complete clear cover after ``no_signal``;
    the caller may then replan from the real response.  A timeout or empty
    finite belief returns the continuous-safe clear action.
    """
    if risk_metric not in ("mean", "p90", "cvar", "worst"):
        raise ValueError("Q4滚动风险指标必须为mean、p90、cvar或worst。")
    if not 0.0 < cvar_alpha < 1.0:
        raise ValueError("Q4滚动CVaR分位必须位于(0,1)。")
    if (scenario_limit < 1 or candidate_limit < 1
            or cpu_time_limit_s <= 0.0 or savings_margin_s < 0.0):
        raise ValueError("Q4滚动上限必须为正数，节省余量不能为负。")
    started = time.perf_counter()
    deadline = started+cpu_time_limit_s
    continuation_points = tuple(tuple(point) for point in continuation_points)
    clear_points = list(
        posterior_clear_points(track.region)
        if remaining_clear_points is None else remaining_clear_points
    )
    clear_now, clear_now_base, _ = _route_cost(
        clear_points, current_position, continuation_points,
    )
    points = list(dict.fromkeys(tuple(point) for point in probe_points))
    if not points:
        return _clear_decision(
            clear_now, reason="no_certified_probe_point",
            elapsed_s=time.perf_counter()-started,
        )
    if belief is None or not belief.scenarios:
        return _clear_decision(
            clear_now, reason="empty_finite_belief", status="fallback",
            elapsed_s=time.perf_counter()-started,
        )

    scenarios = _sample_scenarios(belief.scenarios, scenario_limit)
    ranked_starts = sorted(points, key=lambda point: (
        -sum(
            weight for scenario, weight in scenarios
            if is_visible(
                scenario.position, scenario.direction_deg, point,
                scenario.receive_radius,
            )
        ),
        measure_cost(
            current_position, point, current_channel, track.channel,
        ).total_s,
        point,
    ))[:candidate_limit]

    current_radius = track.region["minimum_enclosing_circle"]["radius"]
    base_clear_cache = {}
    posterior_cache = {}

    def base_clear_from(point):
        key = _point_key(point)
        if key not in base_clear_cache:
            _, base, _ = _route_cost(clear_points, point)
            base_clear_cache[key] = base
        return base_clear_cache[key]

    def direction_future(point, target, error):
        key = (_point_key(point), _point_key(target), float(error))
        if key not in posterior_cache:
            try:
                posterior = _posterior_after_direction(
                    track, point, target, error, config,
                )
                if posterior.get("status") != "bounded":
                    raise RuntimeError("方向分支未形成有界后验。")
                new_radius = posterior["minimum_enclosing_circle"]["radius"]
                future = predicted_clear_cost(
                    base_clear_from(point), current_radius, new_radius,
                )
                if continuation_points:
                    center = tuple(
                        posterior["minimum_enclosing_circle"]["center"]
                    )
                    future += min(
                        math.dist(center, other)
                        for other in continuation_points
                    )/5.0
                posterior_cache[key] = future
            except (RuntimeError, ValueError, KeyError, ZeroDivisionError):
                posterior_cache[key] = base_clear_from(point)
        return posterior_cache[key]

    evaluated = []
    timed_out = False
    for first in ranked_starts:
        if time.perf_counter() >= deadline:
            timed_out = True
            break
        full_order = _probe_order(
            points, scenarios,
            current_position=current_position,
            current_channel=current_channel,
            target_channel=track.channel,
            forced_first=first,
        )
        order = full_order[:1] if one_step_replan else full_order
        prefix_costs = []
        previous = tuple(current_position)
        channel = current_channel
        running = 0.0
        for point in order:
            running += measure_cost(
                previous, point, channel, track.channel,
            ).total_s
            prefix_costs.append(running)
            previous = point
            channel = track.channel

        values = []
        complete = True
        for scenario, weight in scenarios:
            if time.perf_counter() >= deadline:
                timed_out = True
                complete = False
                break
            visible_index = next((
                index for index, point in enumerate(order)
                if is_visible(
                    scenario.position, scenario.direction_deg, point,
                    scenario.receive_radius,
                )
            ), None)
            if visible_index is None:
                last = order[-1]
                future = base_clear_from(last)
                values.append((prefix_costs[-1]+future, weight))
                continue
            point = order[visible_index]
            prefix = prefix_costs[visible_index]
            if math.dist(point, scenario.position) <= 5.0+1e-9:
                continuation = (
                    min(math.dist(point, other)
                        for other in continuation_points)/5.0
                    if continuation_points else 0.0
                )
                values.append((prefix+5.0+continuation, weight))
                continue
            for error in (-config.error_deg, 0.0, config.error_deg):
                values.append((
                    prefix+direction_future(
                        point, scenario.position, error,
                    ),
                    weight/3.0,
                ))
        if not complete:
            break
        risk_cost, risk = _weighted_risk(values, risk_metric, cvar_alpha)
        evaluated.append({
            "selected_point": first,
            "probe_order": order,
            "estimated_total_cost_s": risk_cost,
            "estimated_saving_s": clear_now-risk_cost,
            "risk_summary_s": risk,
            "scenario_count": len(scenarios),
        })

    elapsed = time.perf_counter()-started
    if not evaluated:
        return _clear_decision(
            clear_now,
            reason=("time_limit_before_complete_sequence" if timed_out
                    else "no_complete_sequence"),
            status="fallback", timed_out=timed_out, elapsed_s=elapsed,
        )
    best = min(evaluated, key=lambda item: (
        item["estimated_total_cost_s"], item["selected_point"],
    ))
    if best["estimated_total_cost_s"]+savings_margin_s >= clear_now:
        decision = _clear_decision(
            clear_now, reason="risk_adjusted_probe_not_better",
            status="partial" if timed_out else "ok",
            timed_out=timed_out,
            evaluated_sequence_count=len(evaluated), elapsed_s=elapsed,
        )
        decision["best_rejected_sequence"] = best
        return decision
    return {
        "decision": "measure",
        "selected_point": best["selected_point"],
        "probe_order": best["probe_order"],
        "clear_now_cost_s": clear_now,
        "clear_now_base_cost_s": clear_now_base,
        "estimated_total_cost_s": best["estimated_total_cost_s"],
        "estimated_saving_s": best["estimated_saving_s"],
        "risk_summary_s": best["risk_summary_s"],
        "risk_metric": risk_metric,
        "scenario_count": best["scenario_count"],
        "reason": "risk_adjusted_probe_saving",
        "solver_status": "partial" if timed_out else "ok",
        "timed_out": timed_out,
        "evaluated_sequence_count": len(evaluated),
        "cpu_wall_time_s": elapsed,
        "horizon_mode": "one_step" if one_step_replan else "bundle",
    }
