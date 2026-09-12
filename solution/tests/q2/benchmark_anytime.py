"""Standalone anytime budget benchmark for Q2 planning (not part of strategy).

Runs planning on three representative regions under budgets 6/60/300 s and
prints a comparison of ``worst_case_radius_m`` versus measured wall time, to
check whether more compute yields a better point.  The FIM sub-budget is
raised together with the unified wall-clock budget so that the budget is the
only limiter; the region sampling (plot-only near-optimal regions) is
disabled to keep the benchmark on the decision path.
"""

import argparse
from pathlib import Path
import sys
import time

SOLUTION = Path(__file__).resolve().parents[2]
SRC = SOLUTION / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import json

from common.models import BearingObservation
from q2.planner import Q2Config, plan_second_point

REPRESENTATIVE_CASES = {
    "near_field": {
        "position": (-600.0, -300.0),
        "bearing_deg": 35.89,
        "note": "第一检测点在盘内偏近，源区域为窄楔形",
    },
    "mid_field": {
        "position": (300.0, 400.0),
        "bearing_deg": 120.0,
        "note": "第一检测点在盘内中部，源区域中宽",
    },
    "far_field": {
        "position": (800.0, 0.0),
        "bearing_deg": 0.0,
        "note": "第一检测点靠近区域边缘，源区域向边界延伸",
    },
}


def run_case(name, case, budget_s):
    observation = BearingObservation(tuple(case["position"]), 1, "direction",
                                     case["bearing_deg"])
    config = Q2Config(
        planning_wall_clock_budget_s=budget_s,
        fim_cpu_time_limit_s=budget_s,
        near_optimal_region_mode="off",
    )
    started = time.perf_counter()
    plan = plan_second_point(observation, config=config)
    wall = time.perf_counter() - started
    fim = plan["continuous_fim"]
    return {
        "case": name,
        "budget_s": budget_s,
        "planning_wall_time_used_s": plan["planning_wall_time_used_s"],
        "measured_wall_s": round(wall, 3),
        "worst_case_radius_m": plan["selected"]["worst_case_radius_m"],
        "action_time_s": plan["selected"]["action_time_s"],
        "recommendation_source": plan["recommendation_source"],
        "selected_point": [round(v, 2) for v in plan["selected_point"]],
        "fim_status": fim["status"],
        "fim_timed_out": fim.get("timed_out"),
        "fim_iteration_count": fim.get("iteration_count"),
        "planning_timed_out": plan["planning_timed_out"],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Anytime 预算基准：3 区域性区域 × 预算 6/60/300s",
    )
    parser.add_argument("--budgets", type=float, nargs="+", default=[6.0, 60.0, 300.0])
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name(
        "analysis") / "anytime_budget_comparison.json")
    args = parser.parse_args(argv)
    results = []
    for name, case in REPRESENTATIVE_CASES.items():
        for budget in args.budgets:
            results.append(run_case(name, case, budget))
    print("=" * 96)
    print(f"{'区域':<10}{'预算s':>6}{'墙钟s':>8}{'worst_radius':>12}"
          f"{'动作s':>8}{'FIM_src':>10}{'FIM截断':>8}{'规划截断':>8}")
    print("-" * 96)
    for row in results:
        print(f"{row['case']:<10}{row['budget_s']:>6.0f}"
              f"{row['measured_wall_s']:>8.2f}"
              f"{row['worst_case_radius_m']:>12.2f}"
              f"{row['action_time_s']:>8.2f}"
              f"{row['recommendation_source']:>10}"
              f"{str(row['fim_timed_out']):>8}"
              f"{str(row['planning_timed_out']):>8}")
    print("=" * 96)
    for name, case in REPRESENTATIVE_CASES.items():
        budgets = [r for r in results if r["case"] == name]
        radii = {r["budget_s"]: r["worst_case_radius_m"] for r in budgets}
        best = min(radii.values())
        print(f"{name}: 预算 6/60/300s → worst_radius "
              f"{radii[6.0]:.2f}/{radii[60.0]:.2f}/{radii[300.0]:.2f} m，"
              f"最优 {best:.2f} m；{case['note']}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    payload = {"cases": REPRESENTATIVE_CASES, "results": results}
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                           encoding="utf-8")
    print(f"wrote: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())