"""Q2-generated candidates filtered through Q4 directional objectives.

The functions in this module only add optional first-probe candidates.  They
never remove points from the certified directional bundle, so a sequence of
``no_signal`` responses still falls back to the original geometric proof.
"""

import math

from common.time_model import measure_cost


def _point_key(point):
    return round(point[0], 8), round(point[1], 8)


def _add_candidate(items, by_point, item, source):
    if not item:
        return
    point = item.get("point", item.get("selected_point"))
    if point is None:
        return
    point = tuple(float(value) for value in point)
    if len(point) != 2 or not all(math.isfinite(value) for value in point):
        return
    key = _point_key(point)
    if key in by_point:
        by_point[key]["sources"].add(source)
        return
    record = {
        "point": point,
        "sources": {source},
        "q2_worst_case_radius_m": float(
            item.get("worst_case_radius_m", float("inf"))
        ),
    }
    by_point[key] = record
    items.append(record)


def extract_q2_candidates(plan):
    """Return deduplicated discrete, continuous-FIM and Pareto points."""
    items, by_point = [], {}
    _add_candidate(items, by_point, plan.get("selected"), "top_level")

    baseline = plan.get("baseline", {})
    _add_candidate(items, by_point, baseline.get("selected"), "discrete")
    for item in plan.get("candidates", ()):
        _add_candidate(items, by_point, item, "discrete")

    continuous = plan.get("continuous_fim", {})
    if continuous.get("status") == "ok":
        _add_candidate(
            items, by_point, continuous.get("selected"), "continuous_fim",
        )
        for item in continuous.get("candidates", ()):
            _add_candidate(
                items, by_point, item, "continuous_fim_budget",
            )

    for item in plan.get("pareto_front", ()):
        _add_candidate(items, by_point, item, "q2_pareto")
    return items


def _dominates(first, second):
    fields = (
        "no_signal_weight", "action_time_s", "q2_worst_case_radius_m",
    )
    return (
        all(first[field] <= second[field]+1e-12 for field in fields)
        and any(first[field] < second[field]-1e-12 for field in fields)
    )


def build_integrated_probe_plan(
        certified_points, q2_plan, belief, *, current_position,
        current_channel, target_channel, candidate_limit=4):
    """Append a bounded Q4-static Pareto subset to a certified bundle.

    The static front balances directional ``no_signal`` mass, immediate
    action time and Q2's set-based post-measurement radius.  The downstream
    Q4 rolling evaluator then recomputes full joint-scenario clear cost and a
    second, Q4-specific Pareto front.
    """
    if candidate_limit < 1:
        raise ValueError("Q4接入的Q2候选上限至少为1。")
    certified = list(dict.fromkeys(
        tuple(float(value) for value in point)
        for point in certified_points
    ))
    certified_keys = {_point_key(point) for point in certified}
    total_weight = sum(item.weight for item in belief.scenarios)
    candidates = extract_q2_candidates(q2_plan)
    evaluated = []
    for item in candidates:
        point = item["point"]
        visible_weight = (
            belief.visible_weight(point)/total_weight
            if total_weight > 0.0 else 0.0
        )
        radius = item["q2_worst_case_radius_m"]
        if not math.isfinite(radius):
            radius = float(
                q2_plan["region"]["minimum_enclosing_circle"]["radius"]
            )
        evaluated.append({
            **item,
            "sources": sorted(item["sources"]),
            "q2_worst_case_radius_m": radius,
            "visible_weight": visible_weight,
            "no_signal_weight": max(0.0, 1.0-visible_weight),
            "action_time_s": measure_cost(
                current_position, point, current_channel, target_channel,
            ).total_s,
        })
    pareto = [
        item for item in evaluated
        if not any(
            other is not item and _dominates(other, item)
            for other in evaluated
        )
    ]
    pareto.sort(key=lambda item: (
        item["no_signal_weight"], item["action_time_s"],
        item["q2_worst_case_radius_m"], item["point"],
    ))
    selected = pareto[:candidate_limit]

    merged = list(certified)
    source_by_point = {_point_key(point): "certified" for point in certified}
    extra_count = 0
    for item in selected:
        key = _point_key(item["point"])
        source = "+".join(item["sources"])
        if key in source_by_point:
            source_by_point[key] = f"certified+{source}"
            continue
        merged.append(item["point"])
        source_by_point[key] = source
        extra_count += 1
    return {
        "points": merged,
        "source_by_point": source_by_point,
        "q2_candidate_count": len(evaluated),
        "q4_static_pareto_front": selected,
        "extra_point_count": extra_count,
        "certified_point_count": len(certified),
    }
