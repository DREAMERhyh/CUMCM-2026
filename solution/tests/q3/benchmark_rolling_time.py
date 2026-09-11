"""Independent train/validation benchmark for Q3 rolling-time task two."""

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import json
import math
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
from q3.rolling_time import clear_plan_cost
from runtime.runner import run_policy
from sim.fake import FakeSimulator, FakeSource
from tests.q3.benchmark_adaptive import generate_cases


VALIDATION_STRATEGIES = ("baseline", "task1", "task2", "combined")
TRAINING_RISKS = ("p90", "cvar", "worst")


class InstrumentedPolicy(Q3Policy):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.action_modes = {}
        self.rolling_decisions = []
        self.realised_rolling = []
        self.last_state = None

    def initial_state(self):
        self.last_state = super().initial_state()
        return self.last_state

    def _action(self, state, kind, position=None, channel=None, mode=None):
        action = super()._action(state, kind, position, channel, mode)
        self.action_modes[action.request_id] = mode
        return action

    def _rolling_decision(self, state, track, plan):
        result = super()._rolling_decision(state, track, plan)
        self.rolling_decisions.append({
            **result,
            "channel": track.channel,
            "decision_virtual_time_s": state.virtual_time_s,
        })
        return result

    def apply_response(self, state, action, response):
        mode = state.pending_mode
        decision = None
        if (action.kind == "measure"
                and mode in ("refine", "joint_target")
                and action.channel in state.sources):
            candidate = state.sources[action.channel].last_rolling_decision
            if (candidate and candidate.get("decision") == "measure"
                    and tuple(candidate.get("selected_point"))
                    == tuple(action.position)):
                decision = dict(candidate)
        super().apply_response(state, action, response)
        if decision is None:
            return
        continuation_points = [
            tuple(other.region["minimum_enclosing_circle"]["center"])
            for channel, other in sorted(state.sources.items())
            if (channel != action.channel and channel not in state.cleared
                and other.region is not None
                and other.region.get("status") == "bounded")
        ]
        if response["measure_result"] == "near":
            actual_post_clear_s = 5.0 + (
                min(math.dist(action.position, point)
                    for point in continuation_points) / 5.0
                if continuation_points else 0.0
            )
        else:
            actual_post_clear_s = clear_plan_cost(
                state.sources[action.channel].region, action.position,
                continuation_points=continuation_points,
            )["cost_s"]
        realised_saving = (
            decision["clear_now_cost_s"]
            - decision["measure_action_time_s"]
            - actual_post_clear_s
        )
        self.realised_rolling.append({
            "channel": action.channel,
            "predicted_saving_s": decision["estimated_saving_s"],
            "realised_one_step_saving_s": realised_saving,
            "prediction_error_s": (
                decision["estimated_saving_s"] - realised_saving
            ),
        })


def _policy(strategy, risk_metric, fim_limit_s, rolling_limit_s):
    task1 = strategy in ("task1", "combined")
    task2 = strategy in ("task2", "combined")
    return InstrumentedPolicy(
        max_refinements=5,
        fim_cpu_time_limit_s=fim_limit_s,
        adaptive_refinement=True,
        posterior_grid=True,
        joint_batch_mode="guaranteed",
        failed_clear_remeasure_mode="gated" if task1 else "off",
        rolling_time_mode="scenario" if task2 else "off",
        rolling_risk_metric=risk_metric,
        rolling_cpu_time_limit_s=rolling_limit_s,
    )


def _time_breakdown(actions, action_modes):
    position, channel = (0.0, 0.0), 1
    totals = Counter()
    phases = Counter()
    switches = 0
    for entry in actions:
        action, response = entry["action"], entry["response"]
        if action["kind"] == "measure":
            point = (action["position"]["x"], action["position"]["y"])
            timing = measure_cost(position, point, channel, action["channel"])
            if timing.switching_s > 0.0:
                switches += 1
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
        phase = ("scan" if mode in ("scan", "scan_batch")
                 else "clear" if mode in (
                     "fallback_clear", "certified_clear", "near_clear"
                 ) else "localise")
        phases[phase] += timing.total_s
        for name in ("movement_s", "switching_s", "measurement_s",
                     "optical_s", "laser_s"):
            totals[name] += getattr(timing, name)
    totals["movement_distance_m"] = totals["movement_s"] * 5.0
    totals["channel_switch_count"] = switches
    return dict(totals), dict(phases)


def _run_one(task):
    phase, case, strategy, risk_metric, fim_limit_s, rolling_limit_s = task
    policy = _policy(strategy, risk_metric, fim_limit_s, rolling_limit_s)
    sources = [
        FakeSource(item["channel"], tuple(item["position"]),
                   item["receive_radius"])
        for item in case["sources"]
    ]
    expected = sorted(item["channel"] for item in case["sources"])
    started = time.perf_counter()
    try:
        summary = run_policy(policy, FakeSimulator(sources), max_actions=5000)
        totals, phases = _time_breakdown(
            summary.actions, policy.action_modes
        )
        statuses = Counter(
            item.get("solver_status", "unknown")
            for item in policy.rolling_decisions
        )
        decisions = Counter(
            item.get("decision", "unknown")
            for item in policy.rolling_decisions
        )
        errors = [abs(item["prediction_error_s"])
                  for item in policy.realised_rolling]
        return {
            "phase": phase,
            "case_id": case["case_id"],
            "strategy": strategy,
            "risk_metric": risk_metric,
            "complete": summary.cleared_channels == expected,
            "virtual_time_s": summary.virtual_time_s,
            "action_count": len(summary.actions),
            "time_breakdown": totals,
            "phase_time_s": phases,
            "rolling_decisions": dict(decisions),
            "rolling_solver_status": dict(statuses),
            "rolling_prediction_count": len(errors),
            "mean_absolute_prediction_error_s": (
                statistics.fmean(errors) if errors else None
            ),
            "cpu_wall_time_s": time.perf_counter() - started,
            "error": None,
        }
    except Exception as error:
        return {
            "phase": phase,
            "case_id": case["case_id"],
            "strategy": strategy,
            "risk_metric": risk_metric,
            "complete": False,
            "virtual_time_s": None,
            "action_count": None,
            "time_breakdown": {},
            "phase_time_s": {},
            "rolling_decisions": {},
            "rolling_solver_status": {},
            "rolling_prediction_count": 0,
            "mean_absolute_prediction_error_s": None,
            "cpu_wall_time_s": time.perf_counter() - started,
            "error": f"{type(error).__name__}: {error}",
        }


def _p90(values):
    ordered = sorted(values)
    return ordered[max(0, (9 * len(ordered) + 9) // 10 - 1)] if ordered else None


def _summary(rows):
    completed = [row for row in rows if row["complete"]]
    values = [row["virtual_time_s"] for row in completed]
    prediction_errors = [
        row["mean_absolute_prediction_error_s"] for row in rows
        if row["mean_absolute_prediction_error_s"] is not None
    ]
    result = {
        "completed_cases": len(completed),
        "case_count": len(rows),
        "mean_virtual_time_s": statistics.fmean(values) if values else None,
        "median_virtual_time_s": statistics.median(values) if values else None,
        "p90_virtual_time_s": _p90(values),
        "max_virtual_time_s": max(values) if values else None,
        "mean_action_count": statistics.fmean(
            row["action_count"] for row in completed
        ) if completed else None,
        "mean_cpu_wall_time_s": statistics.fmean(
            row["cpu_wall_time_s"] for row in rows
        ),
        "mean_absolute_prediction_error_s": (
            statistics.fmean(prediction_errors) if prediction_errors else None
        ),
    }
    for field in ("scan", "localise", "clear"):
        result[f"mean_{field}_time_s"] = (
            statistics.fmean(
                row["phase_time_s"].get(field, 0.0) for row in completed
            ) if completed else None
        )
    for field in ("movement_distance_m", "channel_switch_count"):
        result[f"mean_{field}"] = (
            statistics.fmean(
                row["time_breakdown"].get(field, 0.0) for row in completed
            ) if completed else None
        )
    result["rolling_decisions"] = dict(sum(
        (Counter(row["rolling_decisions"]) for row in rows), Counter()
    ))
    result["rolling_solver_status"] = dict(sum(
        (Counter(row["rolling_solver_status"]) for row in rows), Counter()
    ))
    return result


def _comparison(cases, rows, baseline_name, candidate_name):
    by_key = {(row["case_id"], row["strategy"]): row for row in rows}
    pairs = []
    for case in cases:
        baseline = by_key[(case["case_id"], baseline_name)]
        candidate = by_key[(case["case_id"], candidate_name)]
        both = baseline["complete"] and candidate["complete"]
        pairs.append({
            "case_id": case["case_id"],
            "both_complete": both,
            "candidate_minus_baseline_virtual_s": (
                candidate["virtual_time_s"] - baseline["virtual_time_s"]
                if both else None
            ),
        })
    deltas = [item["candidate_minus_baseline_virtual_s"]
              for item in pairs if item["both_complete"]]
    extra_incomplete = any(
        by_key[(case["case_id"], baseline_name)]["complete"]
        and not by_key[(case["case_id"], candidate_name)]["complete"]
        for case in cases
    )
    baseline_p90 = _summary([
        by_key[(case["case_id"], baseline_name)] for case in cases
    ])["p90_virtual_time_s"]
    candidate_p90 = _summary([
        by_key[(case["case_id"], candidate_name)] for case in cases
    ])["p90_virtual_time_s"]
    wins = sum(delta < -1e-9 for delta in deltas)
    return {
        "baseline": baseline_name,
        "candidate": candidate_name,
        "valid_pair_count": len(deltas),
        "win_count": wins,
        "win_rate": wins / len(deltas) if deltas else None,
        "mean_virtual_time_delta_s": (
            statistics.fmean(deltas) if deltas else None
        ),
        "has_extra_incomplete_case": extra_incomplete,
        "p90_not_worse": (
            candidate_p90 <= baseline_p90 + 1e-9
            if candidate_p90 is not None and baseline_p90 is not None
            else False
        ),
        "accepted": (
            bool(deltas) and not extra_incomplete
            and statistics.fmean(deltas) < 0.0
            and wins * 2 >= len(deltas)
            and candidate_p90 <= baseline_p90 + 1e-9
        ),
        "pairs": pairs,
    }


def _select_training_risk(cases, rows):
    summaries = {}
    for risk in TRAINING_RISKS:
        risk_rows = [row for row in rows if row["risk_metric"] == risk]
        summaries[risk] = _summary(risk_rows)
    selected = min(TRAINING_RISKS, key=lambda risk: (
        -summaries[risk]["completed_cases"],
        summaries[risk]["p90_virtual_time_s"] or float("inf"),
        summaries[risk]["mean_virtual_time_s"] or float("inf"),
        risk,
    ))
    return selected, summaries


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Q3总虚拟时间滚动优化的独立训练/验证基准"
    )
    parser.add_argument("--train-cases", type=int, default=2)
    parser.add_argument("--validation-cases", type=int, default=4)
    parser.add_argument("--train-seed", type=int, default=20260912)
    parser.add_argument("--validation-seed", type=int, default=20261912)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--fim-cpu-time-limit-s", type=float, default=10.0)
    parser.add_argument("--rolling-cpu-time-limit-s", type=float, default=0.2)
    parser.add_argument(
        "--output", default="output/q3_offline/rolling_time_benchmark.json"
    )
    args = parser.parse_args(argv)
    if (args.train_cases < 1 or args.validation_cases < 1
            or args.workers < 1 or args.fim_cpu_time_limit_s <= 0.0
            or args.rolling_cpu_time_limit_s <= 0.0):
        parser.error("场景数、进程数和两个CPU时限必须为正数。")

    train_cases = generate_cases(args.train_cases, args.train_seed)
    validation_cases = generate_cases(
        args.validation_cases, args.validation_seed
    )
    started = time.perf_counter()
    train_tasks = [
        ("training", case, "combined", risk,
         args.fim_cpu_time_limit_s, args.rolling_cpu_time_limit_s)
        for case in train_cases for risk in TRAINING_RISKS
    ]
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        train_rows = list(executor.map(_run_one, train_tasks))
    selected_risk, training_summaries = _select_training_risk(
        train_cases, train_rows
    )

    validation_tasks = [
        ("validation", case, strategy, selected_risk,
         args.fim_cpu_time_limit_s, args.rolling_cpu_time_limit_s)
        for case in validation_cases for strategy in VALIDATION_STRATEGIES
    ]
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        validation_rows = list(executor.map(_run_one, validation_tasks))
    validation_summaries = {
        strategy: _summary([
            row for row in validation_rows if row["strategy"] == strategy
        ]) for strategy in VALIDATION_STRATEGIES
    }
    comparisons = {
        "task2_vs_baseline": _comparison(
            validation_cases, validation_rows, "baseline", "task2"
        ),
        "combined_vs_task1": _comparison(
            validation_cases, validation_rows, "task1", "combined"
        ),
    }
    report = {
        "offline_only": True,
        "training": {
            "seed": args.train_seed,
            "case_count": args.train_cases,
            "risk_candidates": list(TRAINING_RISKS),
            "selected_risk_metric": selected_risk,
            "summaries": training_summaries,
            "cases": train_cases,
            "results": train_rows,
        },
        "validation": {
            "seed": args.validation_seed,
            "case_count": args.validation_cases,
            "strategies": list(VALIDATION_STRATEGIES),
            "summaries": validation_summaries,
            "comparisons": comparisons,
            "cases": validation_cases,
            "results": validation_rows,
        },
        "fim_cpu_time_limit_s": args.fim_cpu_time_limit_s,
        "rolling_cpu_time_limit_s": args.rolling_cpu_time_limit_s,
        "benchmark_wall_time_s": time.perf_counter() - started,
    }
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({
        "selected_risk_metric": selected_risk,
        "validation_summaries": validation_summaries,
        "comparisons": comparisons,
        "benchmark_wall_time_s": report["benchmark_wall_time_s"],
    }, ensure_ascii=False, indent=2))
    print(f"结果文件：{path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
