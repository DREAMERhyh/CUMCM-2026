"""Paired offline benchmark for Q3 shared-point multi-channel batches."""

import argparse
from concurrent.futures import ProcessPoolExecutor
import json
from pathlib import Path
import statistics
import sys
import time

SRC = Path(__file__).resolve().parents[2] / "src"
ROOT = SRC.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from common.time_model import clear_cost, measure_cost
from q3.policy import Q3Policy
from runtime.runner import run_policy
from sim.fake import FakeSimulator, FakeSource
from tests.q3.benchmark_adaptive import generate_cases


STRATEGIES = ("adaptive", "joint_guaranteed", "joint_all_active")


class InstrumentedQ3Policy(Q3Policy):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.joint_batches = []
        self.mode_counts = {}

    def _start_joint_batch(self, state, plan):
        self.joint_batches.append({
            "point": list(plan["point"]),
            "channels": list(plan["channels"]),
            "estimated_saving_s": plan["estimated_saving_s"],
        })
        return super()._start_joint_batch(state, plan)

    def _action(self, state, kind, position=None, channel=None, mode=None):
        if mode is not None:
            self.mode_counts[mode] = self.mode_counts.get(mode, 0)+1
        return super()._action(state, kind, position, channel, mode)


def _time_breakdown(actions):
    position = (0.0, 0.0)
    channel = 1
    totals = {"movement_s": 0.0, "switching_s": 0.0,
              "measurement_s": 0.0, "optical_s": 0.0,
              "laser_s": 0.0}
    for entry in actions:
        action = entry["action"]
        response = entry["response"]
        kind = action["kind"]
        if kind == "measure":
            point = (action["position"]["x"], action["position"]["y"])
            timing = measure_cost(position, point, channel, action["channel"])
            position, channel = point, action["channel"]
        elif kind == "clear":
            point = (action["position"]["x"], action["position"]["y"])
            timing = clear_cost(
                position, point, response["clear_result"] == "success"
            )
            position = point
        else:
            continue
        for key in totals:
            totals[key] += getattr(timing, key)
    return totals


def _run_one(task):
    case, strategy, fim_limit_s = task
    mode = {
        "adaptive": "off",
        "joint_guaranteed": "guaranteed",
        "joint_all_active": "all_active",
    }[strategy]
    policy = InstrumentedQ3Policy(
        max_refinements=5,
        fim_cpu_time_limit_s=fim_limit_s,
        adaptive_refinement=True,
        posterior_grid=True,
        joint_batch_mode=mode,
        rolling_time_mode="off",
    )
    sources = [FakeSource(item["channel"], tuple(item["position"]),
                          item["receive_radius"])
               for item in case["sources"]]
    expected = sorted(item["channel"] for item in case["sources"])
    started = time.perf_counter()
    try:
        summary = run_policy(policy, FakeSimulator(sources), max_actions=5000)
        return {
            "case_id": case["case_id"], "strategy": strategy,
            "complete": summary.cleared_channels == expected,
            "virtual_time_s": summary.virtual_time_s,
            "action_count": len(summary.actions),
            "time_breakdown": _time_breakdown(summary.actions),
            "mode_counts": policy.mode_counts,
            "joint_batch_count": len(policy.joint_batches),
            "multi_channel_batch_count": sum(
                len(item["channels"]) > 1 for item in policy.joint_batches
            ),
            "joint_batches": policy.joint_batches,
            "cpu_wall_time_s": time.perf_counter()-started,
            "error": None,
        }
    except Exception as error:
        return {
            "case_id": case["case_id"], "strategy": strategy,
            "complete": False, "virtual_time_s": None,
            "action_count": None, "time_breakdown": {},
            "mode_counts": policy.mode_counts,
            "joint_batch_count": len(policy.joint_batches),
            "multi_channel_batch_count": 0,
            "joint_batches": policy.joint_batches,
            "cpu_wall_time_s": time.perf_counter()-started,
            "error": f"{type(error).__name__}: {error}",
        }


def _strategy_summary(rows):
    completed = [row for row in rows if row["complete"]]
    values = [row["virtual_time_s"] for row in completed]
    ordered = sorted(values)
    p90 = (ordered[max(0, (9*len(ordered)+9)//10-1)]
           if ordered else None)
    return {
        "completed_cases": len(completed),
        "case_count": len(rows),
        "mean_virtual_time_s": statistics.fmean(values) if values else None,
        "median_virtual_time_s": statistics.median(values) if values else None,
        "p90_virtual_time_s": p90,
        "max_virtual_time_s": max(values) if values else None,
        "mean_movement_s": (statistics.fmean(
            row["time_breakdown"]["movement_s"] for row in completed
        ) if completed else None),
        "mean_action_count": (statistics.fmean(
            row["action_count"] for row in completed
        ) if completed else None),
        "total_multi_channel_batches": sum(
            row["multi_channel_batch_count"] for row in rows
        ),
        "mean_cpu_wall_time_s": statistics.fmean(
            row["cpu_wall_time_s"] for row in rows
        ),
    }


def summarise(cases, results):
    by_key = {(row["case_id"], row["strategy"]): row for row in results}
    strategies = {
        strategy: _strategy_summary([
            by_key[(case["case_id"], strategy)] for case in cases
        ]) for strategy in STRATEGIES
    }
    comparisons = {}
    for strategy in STRATEGIES[1:]:
        pairs = []
        for case in cases:
            baseline = by_key[(case["case_id"], "adaptive")]
            candidate = by_key[(case["case_id"], strategy)]
            complete = baseline["complete"] and candidate["complete"]
            pairs.append({
                "case_id": case["case_id"],
                "both_complete": complete,
                "candidate_minus_baseline_virtual_s": (
                    candidate["virtual_time_s"]-baseline["virtual_time_s"]
                    if complete else None
                ),
            })
        deltas = [row["candidate_minus_baseline_virtual_s"]
                  for row in pairs if row["both_complete"]]
        extra_failure = any(
            by_key[(case["case_id"], "adaptive")]["complete"]
            and not by_key[(case["case_id"], strategy)]["complete"]
            for case in cases
        )
        wins = sum(delta < -1e-9 for delta in deltas)
        comparisons[strategy] = {
            "valid_pair_count": len(deltas),
            "win_count": wins,
            "win_rate": wins/len(deltas) if deltas else None,
            "mean_virtual_time_delta_s": (
                statistics.fmean(deltas) if deltas else None
            ),
            "has_extra_incomplete_case": extra_failure,
            "accepted": bool(deltas) and not extra_failure
                        and statistics.fmean(deltas) < 0.0
                        and wins*2 >= len(deltas),
            "pairs": pairs,
        }
    return {"strategies": strategies, "comparisons": comparisons}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Q3联合批测离线配对")
    parser.add_argument("--cases", type=int, default=4)
    parser.add_argument("--seed", type=int, default=20260911)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--fim-cpu-time-limit-s", type=float, default=10.0)
    parser.add_argument("--output",
                        default="output/q3_offline/joint_benchmark.json")
    args = parser.parse_args(argv)
    if args.cases < 1 or args.workers < 1 or args.fim_cpu_time_limit_s <= 0:
        parser.error("cases、workers和FIM时限必须为正数。")
    cases = generate_cases(args.cases, args.seed)
    tasks = [(case, strategy, args.fim_cpu_time_limit_s)
             for case in cases for strategy in STRATEGIES]
    started = time.perf_counter()
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        results = list(executor.map(_run_one, tasks))
    report = {
        "offline_only": True,
        "seed": args.seed,
        "case_count": args.cases,
        "strategies": list(STRATEGIES),
        "fim_cpu_time_limit_s": args.fim_cpu_time_limit_s,
        "benchmark_wall_time_s": time.perf_counter()-started,
        "cases": cases,
        "results": results,
        "summary": summarise(cases, results),
    }
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"结果文件：{path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
