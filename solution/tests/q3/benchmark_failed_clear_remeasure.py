"""Paired offline benchmark for failed-clear gated remeasurement."""

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


STRATEGIES = ("baseline", "failed_clear_remeasure")


class InstrumentedPolicy(Q3Policy):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.action_modes = {}

    def _action(self, state, kind, position=None, channel=None, mode=None):
        action = super()._action(state, kind, position, channel, mode)
        self.action_modes[action.request_id] = mode
        return action


def _time_breakdown(actions, action_modes):
    position = (0.0, 0.0)
    channel = 1
    totals = {
        "movement_s": 0.0,
        "switching_s": 0.0,
        "measurement_s": 0.0,
        "optical_s": 0.0,
        "laser_s": 0.0,
    }
    fallback = {key: 0.0 for key in totals}
    fallback_modes = {
        "fallback_clear", "fallback_remeasure",
        "certified_clear", "near_clear",
    }
    for entry in actions:
        action = entry["action"]
        response = entry["response"]
        if action["kind"] == "measure":
            point = (action["position"]["x"], action["position"]["y"])
            timing = measure_cost(position, point, channel, action["channel"])
            position, channel = point, action["channel"]
        elif action["kind"] == "clear":
            point = (action["position"]["x"], action["position"]["y"])
            timing = clear_cost(
                position, point,
                response["clear_result"] == "success",
            )
            position = point
        else:
            continue
        mode = action_modes.get(action["request_id"])
        for key in totals:
            value = getattr(timing, key)
            totals[key] += value
            if mode in fallback_modes:
                fallback[key] += value
    return totals, {**fallback, "total_s": sum(fallback.values())}


def _run_one(task):
    case, strategy, fim_limit_s = task
    policy = InstrumentedPolicy(
        max_refinements=5,
        fim_cpu_time_limit_s=fim_limit_s,
        adaptive_refinement=True,
        posterior_grid=True,
        joint_batch_mode="guaranteed",
        rolling_time_mode="off",
        failed_clear_remeasure_mode=(
            "off" if strategy == "baseline" else "gated"
        ),
    )
    sources = [
        FakeSource(item["channel"], tuple(item["position"]),
                   item["receive_radius"])
        for item in case["sources"]
    ]
    expected = sorted(item["channel"] for item in case["sources"])
    started = time.perf_counter()
    try:
        summary = run_policy(policy, FakeSimulator(sources), max_actions=5000)
        totals, fallback = _time_breakdown(
            summary.actions, policy.action_modes
        )
        modes = [
            policy.action_modes.get(item["action"]["request_id"])
            for item in summary.actions
        ]
        failed_clears = sum(
            mode == "fallback_clear"
            and item["response"].get("clear_result") == "no_target_in_range"
            for mode, item in zip(modes, summary.actions)
        )
        remeasure_results = [
            item["response"].get("measure_result")
            for mode, item in zip(modes, summary.actions)
            if mode == "fallback_remeasure"
        ]
        return {
            "case_id": case["case_id"],
            "strategy": strategy,
            "complete": summary.cleared_channels == expected,
            "virtual_time_s": summary.virtual_time_s,
            "action_count": len(summary.actions),
            "time_breakdown": totals,
            "fallback_phase_time": fallback,
            "failed_fallback_clear_count": failed_clears,
            "fallback_remeasure_count": len(remeasure_results),
            "valid_fallback_remeasure_count": sum(
                result in ("direction", "near")
                for result in remeasure_results
            ),
            "cpu_wall_time_s": time.perf_counter()-started,
            "error": None,
        }
    except Exception as error:
        return {
            "case_id": case["case_id"],
            "strategy": strategy,
            "complete": False,
            "virtual_time_s": None,
            "action_count": None,
            "time_breakdown": {},
            "fallback_phase_time": {},
            "failed_fallback_clear_count": None,
            "fallback_remeasure_count": None,
            "valid_fallback_remeasure_count": None,
            "cpu_wall_time_s": time.perf_counter()-started,
            "error": f"{type(error).__name__}: {error}",
        }


def _p90(values):
    ordered = sorted(values)
    return ordered[max(0, (9*len(ordered)+9)//10-1)] if ordered else None


def _strategy_summary(rows):
    completed = [row for row in rows if row["complete"]]
    values = [row["virtual_time_s"] for row in completed]
    return {
        "completed_cases": len(completed),
        "case_count": len(rows),
        "mean_virtual_time_s": statistics.fmean(values) if values else None,
        "median_virtual_time_s": statistics.median(values) if values else None,
        "p90_virtual_time_s": _p90(values),
        "max_virtual_time_s": max(values) if values else None,
        "mean_fallback_phase_time_s": (
            statistics.fmean(
                row["fallback_phase_time"]["total_s"] for row in completed
            ) if completed else None
        ),
        "mean_failed_fallback_clears": (
            statistics.fmean(
                row["failed_fallback_clear_count"] for row in completed
            ) if completed else None
        ),
        "total_fallback_remeasures": sum(
            row["fallback_remeasure_count"] or 0 for row in rows
        ),
        "total_valid_fallback_remeasures": sum(
            row["valid_fallback_remeasure_count"] or 0 for row in rows
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
        ])
        for strategy in STRATEGIES
    }
    pairs = []
    for case in cases:
        baseline = by_key[(case["case_id"], "baseline")]
        candidate = by_key[(case["case_id"], "failed_clear_remeasure")]
        both_complete = baseline["complete"] and candidate["complete"]
        pairs.append({
            "case_id": case["case_id"],
            "both_complete": both_complete,
            "candidate_minus_baseline_virtual_s": (
                candidate["virtual_time_s"]-baseline["virtual_time_s"]
                if both_complete else None
            ),
        })
    deltas = [
        item["candidate_minus_baseline_virtual_s"]
        for item in pairs if item["both_complete"]
    ]
    extra_failure = any(
        by_key[(case["case_id"], "baseline")]["complete"]
        and not by_key[(case["case_id"], "failed_clear_remeasure")]["complete"]
        for case in cases
    )
    mean_delta = statistics.fmean(deltas) if deltas else None
    wins = sum(delta < -1e-9 for delta in deltas)
    candidate_p90 = strategies["failed_clear_remeasure"][
        "p90_virtual_time_s"
    ]
    baseline_p90 = strategies["baseline"]["p90_virtual_time_s"]
    accepted = (
        bool(deltas)
        and not extra_failure
        and mean_delta < 0.0
        and wins*2 >= len(deltas)
        and candidate_p90 <= baseline_p90+1e-9
    )
    return {
        "strategies": strategies,
        "comparison": {
            "valid_pair_count": len(deltas),
            "win_count": wins,
            "win_rate": wins/len(deltas) if deltas else None,
            "mean_virtual_time_delta_s": mean_delta,
            "has_extra_incomplete_case": extra_failure,
            "accepted": accepted,
            "pairs": pairs,
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Q3清除失败条件复测离线配对"
    )
    parser.add_argument("--cases", type=int, default=8)
    parser.add_argument("--seed", type=int, default=20260911)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--fim-cpu-time-limit-s", type=float, default=10.0)
    parser.add_argument(
        "--output",
        default="output/q3_offline/failed_clear_remeasure_benchmark.json",
    )
    args = parser.parse_args(argv)
    if args.cases < 1 or args.workers < 1 or args.fim_cpu_time_limit_s <= 0:
        parser.error("cases、workers和FIM时限必须为正数。")
    cases = generate_cases(args.cases, args.seed)
    tasks = [
        (case, strategy, args.fim_cpu_time_limit_s)
        for case in cases for strategy in STRATEGIES
    ]
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
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"结果文件：{path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
