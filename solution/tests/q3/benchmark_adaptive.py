"""Paired offline benchmark for Q3 adaptive and interleaved strategies."""

import argparse
from concurrent.futures import ProcessPoolExecutor
import json
import math
from pathlib import Path
import random
import sys
import time

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from q3.policy import Q3Policy
from runtime.runner import run_policy
from sim.fake import FakeSimulator, FakeSource


class InterleavedQ3Policy(Q3Policy):
    """Rejected Part 2 retained only to reproduce the paired benchmark."""

    def __init__(self, *, local_action_quota=2, **kwargs):
        super().__init__(**kwargs)
        self.local_action_quota = local_action_quota

    def _scan_action(self, state):
        while state.scan_point_index < len(self.coverage_points):
            if not state.scan_order:
                state.scan_order = [state.current_channel] + [
                    channel for channel in range(1, 21)
                    if channel != state.current_channel
                ]
                state.scan_channel_index = 0
            while state.scan_channel_index < len(state.scan_order):
                channel = state.scan_order[state.scan_channel_index]
                if channel in state.cleared or channel in state.sources:
                    state.scan_channel_index += 1
                    continue
                return self._action(
                    state, "measure",
                    self.coverage_points[state.scan_point_index],
                    channel, "scan",
                )
            state.scan_point_index += 1
            state.scan_order = []
            if (state.scan_point_index < len(self.coverage_points)
                    and any(channel not in state.cleared
                            for channel in state.sources)):
                state.phase = "local"
                state.local_actions_remaining = self.local_action_quota
                return self._resolve_action(state, allow_exit=False)
        state.absent = set(range(1, 21))-set(state.sources)-state.cleared
        state.phase = "resolve"
        return None

    def next_action(self, state):
        if state.pending is not None:
            return state.pending
        if state.phase != "local":
            return super().next_action(state)
        if state.local_actions_remaining <= 0:
            state.phase = "scan"
            return super().next_action(state)
        action = self._resolve_action(state, allow_exit=False)
        if action is not None:
            return action
        state.phase = "scan"
        return super().next_action(state)

    def apply_response(self, state, action, response):
        was_local = (state.phase == "local"
                     and action.kind in ("measure", "clear"))
        super().apply_response(state, action, response)
        if was_local:
            state.local_actions_remaining -= 1


def generate_cases(count, seed):
    rng = random.Random(seed)
    cases = []
    for case_id in range(count):
        source_count = rng.randint(10, 16)
        channels = rng.sample(range(1, 21), source_count)
        sources = []
        for channel in channels:
            radius = 1800.0*math.sqrt(rng.random())
            angle = 2.0*math.pi*rng.random()
            sources.append({
                "channel": channel,
                "position": [radius*math.cos(angle),
                             radius*math.sin(angle)],
                "receive_radius": rng.uniform(1000.0, 1500.0),
            })
        cases.append({"case_id": case_id, "sources": sources})
    return cases


def _run_one(task):
    case, strategy, fim_limit_s = task
    sources = [FakeSource(item["channel"], tuple(item["position"]),
                          item["receive_radius"])
               for item in case["sources"]]
    if strategy == "legacy":
        policy = Q3Policy(max_refinements=2,
                          rolling_time_mode="off",
                          fim_cpu_time_limit_s=fim_limit_s,
                          adaptive_refinement=False,
                          posterior_grid=False,
                          joint_batch_mode="off")
    elif strategy == "adaptive":
        policy = Q3Policy(max_refinements=5,
                          rolling_time_mode="off",
                          fim_cpu_time_limit_s=fim_limit_s,
                          adaptive_refinement=True,
                          posterior_grid=True,
                          joint_batch_mode="off")
    else:
        policy = InterleavedQ3Policy(
            rolling_time_mode="off",
            max_refinements=5,
            fim_cpu_time_limit_s=fim_limit_s,
            adaptive_refinement=True,
            posterior_grid=True,
            joint_batch_mode="off",
            local_action_quota=2,
        )
    started = time.perf_counter()
    expected = sorted(item["channel"] for item in case["sources"])
    try:
        summary = run_policy(policy, FakeSimulator(sources), max_actions=5000)
        kinds = {}
        for entry in summary.actions:
            kind = entry["action"]["kind"]
            kinds[kind] = kinds.get(kind, 0) + 1
        return {
            "case_id": case["case_id"],
            "strategy": strategy,
            "complete": summary.cleared_channels == expected,
            "cleared_channels": summary.cleared_channels,
            "expected_channels": expected,
            "virtual_time_s": summary.virtual_time_s,
            "action_count": len(summary.actions),
            "action_kinds": kinds,
            "cpu_wall_time_s": time.perf_counter()-started,
            "error": None,
        }
    except Exception as error:  # benchmark must retain failed cases as evidence
        return {
            "case_id": case["case_id"],
            "strategy": strategy,
            "complete": False,
            "cleared_channels": [],
            "expected_channels": expected,
            "virtual_time_s": None,
            "action_count": None,
            "action_kinds": {},
            "cpu_wall_time_s": time.perf_counter()-started,
            "error": f"{type(error).__name__}: {error}",
        }


def summarise(cases, results):
    by_key = {(item["case_id"], item["strategy"]): item
              for item in results}
    strategies = {}
    for strategy in ("legacy", "adaptive", "interleaved"):
        rows = [by_key[(case["case_id"], strategy)] for case in cases]
        completed = [row for row in rows if row["complete"]]
        strategies[strategy] = {
            "completed_cases": len(completed),
            "case_count": len(rows),
            "mean_virtual_time_s": (
                sum(row["virtual_time_s"] for row in completed)/len(completed)
                if completed else None
            ),
            "mean_cpu_wall_time_s": (
                sum(row["cpu_wall_time_s"] for row in rows)/len(rows)
            ),
        }
    paired = []
    for case in cases:
        first = by_key[(case["case_id"], "adaptive")]
        second = by_key[(case["case_id"], "interleaved")]
        paired.append({
            "case_id": case["case_id"],
            "both_complete": first["complete"] and second["complete"],
            "interleaved_minus_adaptive_virtual_s": (
                second["virtual_time_s"]-first["virtual_time_s"]
                if first["complete"] and second["complete"] else None
            ),
        })
    valid = [item["interleaved_minus_adaptive_virtual_s"]
             for item in paired if item["both_complete"]]
    win_count = sum(delta < -1e-9 for delta in valid)
    second_has_extra_failure = any(
        by_key[(case["case_id"], "adaptive")]["complete"]
        and not by_key[(case["case_id"], "interleaved")]["complete"]
        for case in cases
    )
    mean_delta = sum(valid)/len(valid) if valid else None
    negative = (second_has_extra_failure or not valid
                or mean_delta is None or mean_delta >= 0.0
                or win_count*2 < len(valid))
    return {
        "strategies": strategies,
        "paired_interleaving": {
            "valid_pair_count": len(valid),
            "interleaved_win_count": win_count,
            "interleaved_win_rate": win_count/len(valid) if valid else None,
            "mean_virtual_time_delta_s": mean_delta,
            "has_extra_incomplete_case": second_has_extra_failure,
            "negative_optimization": negative,
            "acceptance_rule": (
                "reject if it adds an incomplete case, has nonnegative mean "
                "virtual-time delta, or wins fewer than half of valid pairs"
            ),
        },
        "pairs": paired,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Q3 两部分离线配对测试")
    parser.add_argument("--cases", type=int, default=6)
    parser.add_argument("--seed", type=int, default=20260911)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--fim-cpu-time-limit-s", type=float, default=10.0)
    parser.add_argument("--output", default="output/q3_offline/strategy_benchmark.json")
    args = parser.parse_args(argv)
    if args.cases < 1 or args.workers < 1 or args.fim_cpu_time_limit_s <= 0:
        parser.error("cases、workers 和 FIM 时限都必须为正数。")
    cases = generate_cases(args.cases, args.seed)
    tasks = [(case, strategy, args.fim_cpu_time_limit_s)
             for case in cases
             for strategy in ("legacy", "adaptive", "interleaved")]
    started = time.perf_counter()
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        results = list(executor.map(_run_one, tasks))
    report = {
        "offline_only": True,
        "seed": args.seed,
        "case_count": args.cases,
        "sources_per_case": "uniform integer 10..16",
        "receive_radius_m": "uniform 1000..1500",
        "fim_cpu_time_limit_s": args.fim_cpu_time_limit_s,
        "benchmark_cpu_wall_time_s": time.perf_counter()-started,
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
