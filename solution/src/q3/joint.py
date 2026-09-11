"""Virtual-time scoring helpers for Q3 shared-point batch measurements."""

import math

from q2.planner import score_candidates

from .adaptive import posterior_clear_points, worst_case_clear_cost


def direct_clear_cost(region, start):
    """Conservative virtual cost of exhausting the posterior clear cover."""
    points = posterior_clear_points(region)
    return worst_case_clear_cost(points, start), points


def predicted_clear_cost(current_cost_s, current_radius_m,
                         predicted_radius_m):
    """Scale current cover cost by the squared enclosing-radius ratio."""
    if not math.isfinite(predicted_radius_m):
        return current_cost_s
    if current_radius_m <= 0.0:
        return 5.0
    ratio = min(1.0, max(0.0, predicted_radius_m/current_radius_m))
    return max(5.0, current_cost_s*ratio*ratio)


def fixed_point_evaluation(track, point, *, current_channel, config):
    """Evaluate one already-reached point for one source channel."""
    return score_candidates(
        track.region,
        track.observations,
        [tuple(point)],
        tuple(point),
        current_channel,
        track.channel,
        config,
    )[0]


def marginal_saving(clear_now_s, current_radius_m, evaluation):
    """Estimated virtual seconds saved by one measurement at a fixed point."""
    future = predicted_clear_cost(
        clear_now_s,
        current_radius_m,
        evaluation["worst_case_radius_m"],
    )
    return clear_now_s-evaluation["action_time_s"]-future
