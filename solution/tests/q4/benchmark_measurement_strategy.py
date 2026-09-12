"""Paired ablation for Q4 remeasurement and directional rolling gates."""

import argparse
import json
import math
from pathlib import Path
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from q4.policy import Q4Policy
from sim.fake import FakeSimulator, FakeSource
from tests.q4.benchmark_scan import make_cases


MODES = {
    "baseline": {
        "failed_clear_remeasure_mode": "off",
        "directional_rolling_mode": "off",
    },
    "remeasure_only": {
        "failed_clear_remeasure_mode": "gated",
        "directional_rolling_mode": "off",
    },
    "rolling_only": {
        "failed_clear_remeasure_mode": "off",
        "directional_rolling_mode": "scenario",
    },
    "combined": {
        "failed_clear_remeasure_mode": "gated",
        "directional_rolling_mode": "scenario",
    },
}


def run_case(case, mode, max_actions, rolling_cpu_time_limit_s):
    client = FakeSimulator([
        FakeSource(
            item["channel"], tuple(item["position"]),
            item["receive_radius"], item["direction_deg"],
        )
        for item in case["sources"]
    ])
    policy = Q4Policy(max_refinements=2, scan_mode="triangular37",
                      long_clear_tail_mode="off",
                      directional_rolling_cpu_time_limit_s=(
                          rolling_cpu_time_limit_s
                      ),
                      **MODES[mode])
    state = policy.initial_state()
    records = []
    started = time.perf_counter()
    for _ in range(max_actions):
        action = policy.next_action(state)
        pending_mode = state.pending_mode
        response = client.execute(action)
        records.append((action, response, pending_mode))
        policy.apply_response(state, action, response)
        if action.kind == "exit" and response.get("accepted") is True:
            break
    else:
        raise RuntimeError("Q4消融达到动作上限仍未退出。")
    elapsed = time.perf_counter()-started
    source_channels = {item["channel"] for item in case["sources"]}
    movement_m = 0.0
    position = (0.0, 0.0)
    for action, _, _ in records:
        if action.position is None:
            continue
        movement_m += math.dist(position, action.position)
        position = action.position
    return {
        "mode": mode,
        "source_count": len(source_channels),
        "complete_clear": state.cleared == source_channels,
        "absent_certificate_correct": (
            state.absent == set(range(1, 21))-source_channels
        ),
        "action_count": len(records),
        "measurement_count": sum(
            action.kind == "measure" for action, _, _ in records
        ),
        "directional_probe_count": sum(
            pending_mode == "directional_probe"
            for _, _, pending_mode in records
        ),
        "failed_clear_remeasure_count": sum(
            pending_mode == "fallback_remeasure"
            for _, _, pending_mode in records
        ),
        "failed_clear_count": sum(
            response.get("clear_result") == "no_target_in_range"
            for _, response, _ in records
        ),
        "movement_distance_m": movement_m,
        "virtual_time_s": state.virtual_time_s,
        "cpu_wall_time_s": elapsed,
        "rolling_decision_count": len(state.rolling_diagnostics),
        "rolling_fallback_count": sum(
            item.get("solver_status") == "fallback"
            for item in state.rolling_diagnostics
        ),
    }


def summarize(rows, mode):
    values = [row[mode] for row in rows]
    result = {
        "complete_cases": sum(item["complete_clear"] for item in values),
        "correct_absent_certificates": sum(
            item["absent_certificate_correct"] for item in values
        ),
    }
    for key in (
        "virtual_time_s", "action_count", "measurement_count",
        "directional_probe_count", "failed_clear_remeasure_count",
        "failed_clear_count", "movement_distance_m", "cpu_wall_time_s",
        "rolling_decision_count", "rolling_fallback_count",
    ):
        result[f"mean_{key}"] = statistics.fmean(
            item[key] for item in values
        )
    result["p90_virtual_time_s"] = sorted(
        item["virtual_time_s"] for item in values
    )[max(0, math.ceil(0.9*len(values))-1)]
    return result


def render_markdown(report):
    lines = [
        "# Q4 原地补测与方向滚动配对消融",
        "",
        "> 本结果来自 FakeSimulator，不代表官方模拟器验收。",
        "",
        f"固定种子：`{report['seed']}`；场景数：{report['case_count']}。",
        "",
        "| 指标 | baseline | remeasure_only | rolling_only | combined |",
        "|---|---:|---:|---:|---:|",
    ]
    metrics = (
        ("完整清除", "complete_cases", ".0f"),
        ("正确无源证书", "correct_absent_certificates", ".0f"),
        ("平均虚拟时间/s", "mean_virtual_time_s", ".3f"),
        ("P90虚拟时间/s", "p90_virtual_time_s", ".3f"),
        ("平均检测数", "mean_measurement_count", ".3f"),
        ("平均方向探测数", "mean_directional_probe_count", ".3f"),
        ("平均原地补测数", "mean_failed_clear_remeasure_count", ".3f"),
        ("平均失败清除数", "mean_failed_clear_count", ".3f"),
        ("平均移动距离/m", "mean_movement_distance_m", ".3f"),
        ("平均墙钟/s", "mean_cpu_wall_time_s", ".6f"),
    )
    for label, key, spec in metrics:
        values = [
            format(report["summaries"][mode][key], spec)
            for mode in MODES
        ]
        lines.append(f"| {label} | " + " | ".join(values) + " |")
    lines.extend([
        "",
        "逐场源参数、完整指标和配对胜负见同名 JSON。",
    ])
    return "\n".join(lines)+"\n"


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=int, default=8)
    parser.add_argument("--seed", type=int, default=20267912)
    parser.add_argument("--max-actions", type=int, default=10000)
    parser.add_argument(
        "--rolling-cpu-time-limit-s", type=float, default=3.0,
    )
    parser.add_argument(
        "--output",
        default="output/q4_offline/measurement_strategy_benchmark.json",
    )
    args = parser.parse_args(argv)
    if (args.cases < 1 or args.max_actions < 1
            or args.rolling_cpu_time_limit_s <= 0.0):
        parser.error("场景数、动作上限和滚动CPU时限必须为正数。")
    cases = make_cases(args.cases, args.seed)
    rows = []
    for case in cases:
        row = {
            "case_index": case["case_index"],
            "sources": case["sources"],
        }
        for mode in MODES:
            row[mode] = run_case(
                case, mode, args.max_actions,
                args.rolling_cpu_time_limit_s,
            )
        rows.append(row)
    summaries = {mode: summarize(rows, mode) for mode in MODES}
    report = {
        "seed": args.seed,
        "case_count": args.cases,
        "max_actions": args.max_actions,
        "rolling_cpu_time_limit_s": args.rolling_cpu_time_limit_s,
        "mode_config": MODES,
        "summaries": summaries,
        "paired_wins_vs_baseline": {
            mode: sum(
                row[mode]["virtual_time_s"]
                < row["baseline"]["virtual_time_s"]
                for row in rows
            )
            for mode in MODES if mode != "baseline"
        },
        "rows": rows,
    }
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    markdown = render_markdown(report)
    path.with_suffix(".md").write_text(markdown, encoding="utf-8")
    print(markdown, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
