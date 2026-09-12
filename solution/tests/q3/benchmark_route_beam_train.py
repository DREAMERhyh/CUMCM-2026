"""Small training-only sweep for the Q3 beam width."""

import argparse
from concurrent.futures import ProcessPoolExecutor
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.q3.benchmark_adaptive import generate_cases
from tests.q3.benchmark_route import _run_one


def main(argv=None):
    parser = argparse.ArgumentParser(description="Q3束宽训练案例扫描")
    parser.add_argument("--cases", type=int, default=1)
    parser.add_argument("--seed", type=int, default=20264912)
    parser.add_argument("--widths", type=int, nargs="+", default=(1, 2, 4))
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--output", default=(
        "output/q3_offline/route_part2_beam_train.json"
    ))
    args = parser.parse_args(argv)
    if (args.cases < 1 or args.workers < 1
            or any(width < 1 for width in args.widths)):
        parser.error("案例数、进程数和束宽必须为正数。")
    cases = generate_cases(args.cases, args.seed)
    tasks, labels = [], []
    for width in args.widths:
        for case in cases:
            tasks.append((
                case, "beam_cached", 10.0, 1.0, 0.25, 1.0,
                4096, width, 512,
            ))
            labels.append((width, case["case_id"]))
    if args.workers == 1:
        rows = [_run_one(task) for task in tasks]
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as executor:
            rows = list(executor.map(_run_one, tasks))
    results = []
    for (width, case_id), row in zip(labels, rows):
        results.append({
            "beam_width": width,
            "case_id": case_id,
            "complete": row["complete"],
            "virtual_time_s": row["virtual_time_s"],
            "cpu_wall_time_s": row["cpu_wall_time_s"],
            "cross_source_movement_distance_m": row[
                "time_breakdown"
            ].get("cross_source_movement_distance_m"),
            "cache_hit_rate": row["cache_stats"]["hit_rate"],
            "beam_expanded_nodes": row["beam_expanded_nodes"],
        })
    by_width = {}
    for width in args.widths:
        selected = [row for row in results if row["beam_width"] == width]
        complete = [row for row in selected if row["complete"]]
        by_width[str(width)] = {
            "completed_cases": len(complete),
            "mean_virtual_time_s": (
                sum(row["virtual_time_s"] for row in complete) / len(complete)
                if complete else None
            ),
            "mean_cpu_wall_time_s": (
                sum(row["cpu_wall_time_s"] for row in selected)
                / len(selected)
            ),
        }
    report = {
        "training_only": True,
        "seed": args.seed,
        "case_count": args.cases,
        "widths": list(args.widths),
        "fixed_parameters": {
            "fim_cpu_time_limit_s": 10.0,
            "rolling_cpu_time_limit_s": 1.0,
            "route_cpu_time_limit_s": 1.0,
            "cache_capacity": 4096,
            "beam_max_expansions": 512,
        },
        "summaries": by_width,
        "results": results,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report["summaries"], ensure_ascii=False, indent=2))
    print(f"训练结果：{output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
