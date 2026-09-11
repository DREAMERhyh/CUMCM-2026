"""Reproducible paired benchmark for Q2 discrete and continuous-FIM plans."""

import argparse
from concurrent.futures import ProcessPoolExecutor
import json
import math
import os
from pathlib import Path
import random
import statistics
import sys
import time


SOLUTION = Path(__file__).resolve().parents[2]
SRC = SOLUTION / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from common.models import BearingObservation
from common.time_model import measure_cost
from q1.geometry import contains
from q2.continuous_fim import bearing_fim_index, build_boundary_scenarios
from q2.planner import Q2Config, plan_second_point


def generate_cases(count, seed):
    """Generate valid first direction observations reproducibly.

    Both the source and first detector are inside the 1800 m target disk.  Their
    distance lies in [100, 1000] m, so every generated source is receivable even
    at the minimum allowed receive radius.  Bearing error is uniform only for
    test-case coverage; the planner itself still uses bounded-error geometry.
    """
    randomizer = random.Random(seed)
    cases = []
    while len(cases) < count:
        source_radius = 1800.0 * math.sqrt(randomizer.random())
        source_angle = randomizer.uniform(0.0, 2.0 * math.pi)
        source = (source_radius * math.cos(source_angle),
                  source_radius * math.sin(source_angle))
        distance = randomizer.uniform(100.0, 1000.0)
        true_bearing = randomizer.uniform(0.0, 360.0)
        radians = math.radians(true_bearing)
        sensor = (source[0] - distance * math.cos(radians),
                  source[1] - distance * math.sin(radians))
        if math.hypot(*sensor) > 1800.0:
            continue
        error = randomizer.uniform(-1.0, 1.0)
        cases.append({
            "case_id": f"B200-{len(cases)+1:03d}",
            "source_for_generation_only": source,
            "first_observation": {
                "position": sensor,
                "channel": randomizer.randint(1, 20),
                "result": "direction",
                "bearing_deg": (true_bearing + error) % 360.0,
            },
            "true_bearing_deg": true_bearing,
            "injected_error_deg": error,
            "source_distance_m": distance,
        })
    return cases


def _robust_fim_at(point, plan, observation, config):
    timing = measure_cost(observation.position, point,
                          observation.channel, observation.channel)
    scenarios = build_boundary_scenarios(
        plan["region"]["vertices"], config.fim_samples_per_edge
    )
    values = [
        bearing_fim_index(observation.position, point, source, timing.total_s)
        for source in scenarios
        if math.dist(observation.position, source) > 5.0 + 1e-9
    ]
    values = [value for value in values if value is not None]
    return min(values) if values else None


def run_case(case):
    observation = BearingObservation(**case["first_observation"])
    # The benchmark compares point-selection algorithms.  Region sampling is
    # disabled here so the 200-case run does not spend time on plot-only data.
    config = Q2Config(near_optimal_region_mode="off")
    plan = plan_second_point(observation, config=config)
    source = tuple(case["source_for_generation_only"])
    if not contains(plan["region"]["planes"], source):
        raise AssertionError(f"{case['case_id']} generated truth left source region")
    baseline = plan["baseline"]["selected"]
    continuous = plan["continuous_fim"]
    result = {
        "case_id": case["case_id"],
        "input": case,
        "baseline": {
            "point": baseline["point"],
            "score": baseline["score"],
            "worst_case_radius_m": baseline["worst_case_radius_m"],
            "action_time_s": baseline["action_time_s"],
            "robust_fim_index_per_s": _robust_fim_at(
                baseline["point"], plan, observation, config
            ),
        },
        "continuous_fim_status": continuous["status"],
    }
    if continuous["status"] == "ok":
        selected = continuous["selected"]
        result["continuous_fim"] = {
            "point": selected["point"],
            "score": selected["score"],
            "worst_case_radius_m": selected["worst_case_radius_m"],
            "action_time_s": selected["action_time_s"],
            "robust_fim_index_per_s": continuous[
                "robust_fim_index_per_s"
            ],
        }
        result["differences_new_minus_baseline"] = {
            "score": selected["score"] - baseline["score"],
            "worst_case_radius_m": (
                selected["worst_case_radius_m"]
                - baseline["worst_case_radius_m"]
            ),
            "action_time_s": selected["action_time_s"]
                             - baseline["action_time_s"],
        }
    return result


def _comparison(values, tolerance=1e-9):
    better = sum(value < -tolerance for value in values)
    tie = sum(abs(value) <= tolerance for value in values)
    worse = len(values) - better - tie
    return {
        "new_better_count": better,
        "tie_count": tie,
        "new_worse_count": worse,
        "new_better_fraction": better / len(values) if values else None,
        "mean_new_minus_baseline": statistics.fmean(values) if values else None,
        "median_new_minus_baseline": statistics.median(values) if values else None,
    }


def summarize(results, *, seed, elapsed_s):
    comparable = [item for item in results
                  if item["continuous_fim_status"] == "ok"]
    score_differences = [
        item["differences_new_minus_baseline"]["score"]
        for item in comparable
    ]
    radius_differences = [
        item["differences_new_minus_baseline"]["worst_case_radius_m"]
        for item in comparable
    ]
    time_differences = [
        item["differences_new_minus_baseline"]["action_time_s"]
        for item in comparable
    ]
    baseline_scores = [item["baseline"]["score"] for item in comparable]
    new_scores = [item["continuous_fim"]["score"] for item in comparable]
    fim_differences = [
        item["continuous_fim"]["robust_fim_index_per_s"]
        - item["baseline"]["robust_fim_index_per_s"]
        for item in comparable
        if item["baseline"]["robust_fim_index_per_s"] is not None
    ]
    return {
        "benchmark": "Q2 discrete baseline vs continuous FIM",
        "seed": seed,
        "generated_case_count": len(results),
        "comparable_case_count": len(comparable),
        "continuous_unavailable_count": len(results) - len(comparable),
        "primary_worst_case_radius_m": {
            "definition": (
                "finite-scenario worst posterior enclosing radius; lower is better"
            ),
            "comparison": _comparison(radius_differences),
            "baseline_mean": statistics.fmean(
                item["baseline"]["worst_case_radius_m"]
                for item in comparable
            ),
            "continuous_fim_mean": statistics.fmean(
                item["continuous_fim"]["worst_case_radius_m"]
                for item in comparable
            ),
            "baseline_median": statistics.median(
                item["baseline"]["worst_case_radius_m"]
                for item in comparable
            ),
            "continuous_fim_median": statistics.median(
                item["continuous_fim"]["worst_case_radius_m"]
                for item in comparable
            ),
        },
        "secondary_operational_score": {
            "definition": (
                "action_time_s + 0.5 * worst_case_radius_m; lower is better"
            ),
            "comparison": _comparison(score_differences),
            "baseline_mean": statistics.fmean(baseline_scores),
            "continuous_fim_mean": statistics.fmean(new_scores),
            "baseline_median": statistics.median(baseline_scores),
            "continuous_fim_median": statistics.median(new_scores),
        },
        "secondary_action_time_s": _comparison(time_differences),
        "fim_objective_higher_is_better": {
            "new_better_count": sum(value > 1e-15 for value in fim_differences),
            "tie_count": sum(abs(value) <= 1e-15 for value in fim_differences),
            "new_worse_count": sum(value < -1e-15 for value in fim_differences),
        },
        "elapsed_wall_time_s": elapsed_s,
        "generation": {
            "source_and_first_detector": "uniform-area source; detector rejected unless inside 1800 m disk",
            "source_detector_distance_m": [100.0, 1000.0],
            "bearing_error_deg": [-1.0, 1.0],
            "current_channel": "same as detected source channel",
            "planner_config": (
                "Q2Config defaults except near_optimal_region_mode='off'"
            ),
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run paired Q2 benchmark.")
    parser.add_argument("--count", type=int, default=200)
    parser.add_argument("--seed", type=int, default=20260911)
    parser.add_argument("--workers", type=int,
                        default=min(16, os.cpu_count() or 1))
    parser.add_argument(
        "--output", type=Path,
        default=Path(__file__).with_name("analysis")
        / "q2_200_case_comparison.json",
    )
    args = parser.parse_args(argv)
    if args.count < 1 or args.workers < 1:
        parser.error("count and workers must be positive")
    cases = generate_cases(args.count, args.seed)
    started = time.perf_counter()
    if args.workers == 1:
        results = [run_case(case) for case in cases]
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as executor:
            results = list(executor.map(run_case, cases, chunksize=1))
    elapsed = time.perf_counter() - started
    payload = {
        "summary": summarize(results, seed=args.seed, elapsed_s=elapsed),
        "cases": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                           encoding="utf-8")
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))
    print(f"wrote: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
