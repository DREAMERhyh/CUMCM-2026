"""Offline comparison of uniform and adaptive circle outer approximations."""

import argparse
import json
import math
from pathlib import Path
import random
import statistics
import sys
import time


SOLUTION = Path(__file__).resolve().parents[2]
SRC = SOLUTION / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from common.domain import build_region_from_observations, circle_outer_planes
from common.models import BearingObservation
from q1.geometry import bearing_planes, contains, intersect_halfplanes
from q2.planner import Q2Config, plan_measurement


def generate_cases(count, seed):
    randomizer = random.Random(seed)
    cases = []
    while len(cases) < count:
        source_radius = 1800.0*math.sqrt(randomizer.random())
        source_angle = randomizer.uniform(0.0, 2.0*math.pi)
        source = (
            source_radius*math.cos(source_angle),
            source_radius*math.sin(source_angle),
        )
        distance = randomizer.uniform(100.0, 1000.0)
        true_bearing = randomizer.uniform(0.0, 360.0)
        angle = math.radians(true_bearing)
        sensor = (
            source[0]-distance*math.cos(angle),
            source[1]-distance*math.sin(angle),
        )
        if math.hypot(*sensor) > 1800.0:
            continue
        error = randomizer.uniform(-1.0, 1.0)
        observation = BearingObservation(
            sensor, randomizer.randint(1, 20), "direction",
            (true_bearing+error) % 360.0,
        )
        cases.append((source, observation))
    return cases


def uniform_region(observation, sides):
    planes = circle_outer_planes((0.0, 0.0), 1800.0, sides)
    planes.extend(circle_outer_planes(observation.position, 1500.0, sides))
    planes.extend(bearing_planes(
        observation.position, observation.bearing_deg, 1.005
    ))
    region = intersect_halfplanes(planes)
    region["planes"] = planes
    region["observation_count"] = 1
    region["approximation"] = {
        "kind": "circumscribed_regular_polygon",
        "circle_sides": sides,
        "conservative": True,
    }
    return region


def adaptive_region(observation, sides):
    return build_region_from_observations(
        [observation], error_deg=1.005, circle_sides=sides
    )


def _timed_builders(observations, sides, repeats):
    """Interleave both builders so cache and CPU-frequency effects are shared."""
    builders = {"uniform": uniform_region, "adaptive": adaptive_region}
    elapsed = {name: [] for name in builders}
    for repeat in range(repeats):
        totals = {name: 0.0 for name in builders}
        for index, observation in enumerate(observations):
            order = ("uniform", "adaptive")
            if (repeat+index) % 2:
                order = tuple(reversed(order))
            for name in order:
                started = time.perf_counter()
                builders[name](observation, sides)
                totals[name] += time.perf_counter()-started
        for name in builders:
            elapsed[name].append(totals[name])
    return {name: statistics.median(values)
            for name, values in elapsed.items()}


def _maximum_circle_excess(region, observation):
    circles = (((0.0, 0.0), 1800.0),
               (observation.position, 1500.0))
    return max(
        0.0,
        max(
            math.dist(vertex, center)-radius
            for center, radius in circles
            for vertex in region["vertices"]
        ),
    )


def _mean(values):
    return statistics.fmean(values) if values else None


def _difference_summary(values, tolerance=1e-9):
    return {
        "adaptive_lower_count": sum(value < -tolerance for value in values),
        "tie_count": sum(abs(value) <= tolerance for value in values),
        "adaptive_higher_count": sum(value > tolerance for value in values),
        "mean_adaptive_minus_uniform": _mean(values),
    }


def compare(sides, cases, plan_count, repeats):
    observations = [observation for _, observation in cases]
    builder_elapsed = _timed_builders(observations, sides, repeats)
    uniform_elapsed = builder_elapsed["uniform"]
    adaptive_elapsed = builder_elapsed["adaptive"]

    uniform_regions = [uniform_region(observation, sides)
                       for observation in observations]
    adaptive_regions = [adaptive_region(observation, sides)
                        for observation in observations]
    nested_failures = 0
    truth_failures = 0
    target_failures = 0
    area_ratios = []
    radius_differences = []
    excess_uniform = []
    excess_adaptive = []
    plane_increases = []
    vertex_increases = []
    for (source, observation), uniform, adaptive in zip(
            cases, uniform_regions, adaptive_regions):
        nested_failures += not all(
            contains(uniform["planes"], vertex)
            for vertex in adaptive["vertices"]
        )
        truth_failures += not (
            contains(uniform["planes"], source)
            and contains(adaptive["planes"], source)
        )
        target_failures += not adaptive["approximation"]["target_met"]
        area_ratios.append(adaptive["area"]/uniform["area"])
        radius_differences.append(
            adaptive["minimum_enclosing_circle"]["radius"]
            - uniform["minimum_enclosing_circle"]["radius"]
        )
        excess_uniform.append(_maximum_circle_excess(uniform, observation))
        excess_adaptive.append(_maximum_circle_excess(adaptive, observation))
        plane_increases.append(
            len(adaptive["planes"])-len(uniform["planes"])
        )
        vertex_increases.append(
            len(adaptive["vertices"])-len(uniform["vertices"])
        )

    config = Q2Config(
        circle_sides=sides, scenario_limit=4,
        continuous_fim_enabled=False, near_optimal_region_mode="off",
    )
    uniform_plan_elapsed = 0.0
    adaptive_plan_elapsed = 0.0
    selected_radius_differences = []
    selected_action_time_differences = []
    for index, ((_, observation), uniform, adaptive) in enumerate(zip(
            cases[:plan_count], uniform_regions[:plan_count],
            adaptive_regions[:plan_count])):
        pairs = ((uniform, "uniform"), (adaptive, "adaptive"))
        if index % 2:
            pairs = tuple(reversed(pairs))
        plans = {}
        for region, name in pairs:
            started = time.perf_counter()
            plans[name] = plan_measurement(
                region, [observation],
                current_position=observation.position,
                current_channel=observation.channel,
                target_channel=observation.channel,
                config=config,
            )
            elapsed = time.perf_counter()-started
            if name == "uniform":
                uniform_plan_elapsed += elapsed
            else:
                adaptive_plan_elapsed += elapsed
        selected_radius_differences.append(
            plans["adaptive"]["selected"]["worst_case_radius_m"]
            - plans["uniform"]["selected"]["worst_case_radius_m"]
        )
        selected_action_time_differences.append(
            plans["adaptive"]["selected"]["action_time_s"]
            - plans["uniform"]["selected"]["action_time_s"]
        )

    return {
        "initial_circle_sides": sides,
        "case_count": len(cases),
        "region_builder": {
            "uniform_total_s": uniform_elapsed,
            "adaptive_total_s": adaptive_elapsed,
            "adaptive_over_uniform_ratio": (
                adaptive_elapsed/uniform_elapsed
                if uniform_elapsed else None
            ),
        },
        "geometry": {
            "nested_failures": nested_failures,
            "generated_truth_containment_failures": truth_failures,
            "radial_target_failures": target_failures,
            "mean_adaptive_area_over_uniform": _mean(area_ratios),
            "mec_radius_change_m": _difference_summary(
                radius_differences
            ),
            "mean_max_circle_excess_uniform_m": _mean(excess_uniform),
            "mean_max_circle_excess_adaptive_m": _mean(excess_adaptive),
            "mean_added_planes": _mean(plane_increases),
            "mean_added_vertices": _mean(vertex_increases),
        },
        "discrete_planner": {
            "case_count": plan_count,
            "uniform_total_s": uniform_plan_elapsed,
            "adaptive_total_s": adaptive_plan_elapsed,
            "adaptive_over_uniform_ratio": (
                adaptive_plan_elapsed/uniform_plan_elapsed
                if uniform_plan_elapsed else None
            ),
            "selected_worst_radius_change_m": _difference_summary(
                selected_radius_differences
            ),
            "selected_action_time_change_s": _difference_summary(
                selected_action_time_differences
            ),
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="离线比较整圆均匀外切与局部自适应外切。"
    )
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--plan-count", type=int, default=20)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--seed", type=int, default=20260912)
    parser.add_argument(
        "--output", type=Path,
        default=SOLUTION/"output"/"q2_arc_refinement_benchmark.json",
    )
    args = parser.parse_args(argv)
    if args.count < 1 or not 0 <= args.plan_count <= args.count:
        parser.error("须满足 count>=1 且 0<=plan-count<=count。")
    if args.repeats < 1:
        parser.error("repeats 必须为正整数。")
    cases = generate_cases(args.count, args.seed)
    result = {
        "benchmark": "Q2 uniform vs adaptive circumscribed source region",
        "official_simulator_used": False,
        "seed": args.seed,
        "region_timing_repeats": args.repeats,
        "comparisons": [
            compare(sides, cases, args.plan_count, args.repeats)
            for sides in (24, 16)
        ],
        "limitations": [
            "All cases are synthetic first-bearing observations.",
            "Both builders preserve the legacy half-plane order so timing isolates refinement overhead.",
            "Planner timing disables continuous FIM and near-optimal regions to isolate set scoring.",
            "Wall-clock timings depend on this machine and are not robot virtual time.",
            "No official simulator was available or used.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"结果已写入 {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

