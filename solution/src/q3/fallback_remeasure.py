"""Gated same-position remeasurement after a failed fallback clear."""

import math

from .adaptive import worst_case_clear_cost
from .joint import fixed_point_evaluation, marginal_saving


def _same_point(first, second, tolerance=1e-7):
    return (abs(first[0]-second[0]) <= tolerance
            and abs(first[1]-second[1]) <= tolerance)


def evaluate_failed_clear_remeasure(
        track, point, remaining_points, *, current_channel, config,
        max_remeasures=3, min_remaining_points=3,
        min_baseline_m=40.0, savings_margin_s=2.0):
    """Return a transparent decision for one post-clear remeasure check.

    The caller invokes this exactly once after each failed fallback clear.  A
    positive result means that measuring the same source channel at the
    already-reached clear point is predicted to save virtual time.
    """
    point = tuple(point)
    remaining_points = [tuple(item) for item in remaining_points]
    decision = {
        "worthwhile": False,
        "reason": None,
        "estimated_saving_s": None,
        "clear_remaining_cost_s": None,
        "evaluation": None,
    }
    if track.region is None or track.region.get("status") != "bounded":
        decision["reason"] = "unbounded_region"
        return decision
    if track.fallback_remeasure_count >= max_remeasures:
        decision["reason"] = "remeasure_limit"
        return decision
    if len(remaining_points) < min_remaining_points:
        decision["reason"] = "too_few_clear_points"
        return decision
    if any(_same_point(point, measured)
           for measured in track.fallback_remeasure_points):
        decision["reason"] = "point_already_remeasured"
        return decision
    if any(_same_point(point, observation.position)
           for observation in track.observations):
        decision["reason"] = "point_already_observed"
        return decision
    if not track.observations:
        decision["reason"] = "no_bearing_observation"
        return decision
    baseline_m = math.dist(point, track.observations[-1].position)
    if baseline_m < min_baseline_m:
        decision["reason"] = "insufficient_baseline"
        return decision

    clear_remaining_s = worst_case_clear_cost(remaining_points, point)
    evaluation = fixed_point_evaluation(
        track, point,
        current_channel=current_channel,
        config=config,
    )
    decision["clear_remaining_cost_s"] = clear_remaining_s
    decision["evaluation"] = evaluation
    if not evaluation["guaranteed_reception"]:
        decision["reason"] = "reception_not_guaranteed"
        return decision
    radius = track.region["minimum_enclosing_circle"]["radius"]
    saving_s = marginal_saving(clear_remaining_s, radius, evaluation)
    decision["estimated_saving_s"] = saving_s
    if saving_s <= savings_margin_s:
        decision["reason"] = "insufficient_saving"
        return decision
    decision["worthwhile"] = True
    decision["reason"] = "predicted_saving"
    return decision
