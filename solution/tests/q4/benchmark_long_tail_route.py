"""Paired Q4 ablation for long-clear-tail control and source routing."""

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
import math
from pathlib import Path
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
for value in (ROOT, SRC):
    if str(value) not in sys.path:
        sys.path.insert(0, str(value))

from q4.policy import Q4Policy
from sim.fake import FakeSimulator, FakeSource
from tests.q4.benchmark_scan import make_cases


MODES = {
    "baseline": {
        "long_clear_tail_mode": "off",
        "multi_source_route_mode": "off",
    },
    "long_tail_only": {
        "long_clear_tail_mode": "adaptive",
        "multi_source_route_mode": "off",
    },
    "route_only": {
        "long_clear_tail_mode": "off",
        "multi_source_route_mode": "insertion_2opt",
    },
    "combined": {
        "long_clear_tail_mode": "adaptive",
        "multi_source_route_mode": "insertion_2opt",
    },
}


def _clear_tail_metrics(records):
    consecutive = 0
    longest = 0
    failed_by_channel = Counter()
    for action, response, _ in records:
        failed = (
            action.kind == "clear"
            and response.get("clear_result") == "no_target_in_range"
        )
        if failed:
            consecutive += 1
            longest = max(longest, consecutive)
            failed_by_channel[action.channel] += 1
        else:
            consecutive = 0
    return longest, max(failed_by_channel.values(), default=0)


def run_case(case, mode, max_actions, rolling_limit_s, route_limit_s):
    client = FakeSimulator([
        FakeSource(
            item["channel"], tuple(item["position"]),
            item["receive_radius"], item["direction_deg"],
        )
        for item in case["sources"]
    ])
    policy = Q4Policy(
        max_refinements=2,
        scan_mode="triangular25",
        failed_clear_remeasure_mode="gated",
        directional_rolling_mode="scenario",
        directional_rolling_risk_metric="cvar",
        directional_rolling_cpu_time_limit_s=rolling_limit_s,
        route_cpu_time_limit_s=route_limit_s,
        **MODES[mode],
    )
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
        raise RuntimeError("Q4长尾/路线消融达到动作上限仍未退出。")
    elapsed = time.perf_counter()-started
    source_channels = {item["channel"] for item in case["sources"]}
    movement_m = 0.0
    position = (0.0, 0.0)
    for action, _, _ in records:
        if action.position is not None:
            movement_m += math.dist(position, action.position)
            position = tuple(action.position)
    longest_run, max_source_failures = _clear_tail_metrics(records)
    rescue_starts = [
        item for item in state.long_clear_diagnostics
        if item.get("event") == "long_clear_rescue_started"
    ]
    return {
        "mode": mode,
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
        "longest_consecutive_failed_clear_run": longest_run,
        "max_failed_clears_for_one_source": max_source_failures,
        "movement_distance_m": movement_m,
        "virtual_time_s": state.virtual_time_s,
        "cpu_wall_time_s": elapsed,
        "long_clear_rescue_count": sum(
            state.long_clear_rescue_counts.values()
        ),
        "long_clear_rescue_started_count": len(rescue_starts),
        "long_clear_rescue_estimated_saving_s": sum(
            item["decision"].get("estimated_saving_s", 0.0)
            for item in rescue_starts
        ),
        "route_planning_call_count": len(policy.route_planning_history),
        "route_fallback_count": sum(
            item.get("status") in ("fallback", "error")
            for item in policy.route_planning_history
        ),
    }


def _run_job(job):
    case, mode, max_actions, rolling_limit_s, route_limit_s = job
    return case["case_index"], mode, run_case(
        case, mode, max_actions, rolling_limit_s, route_limit_s,
    )


def summarize(rows, mode):
    values = [row[mode] for row in rows]
    result = {
        "complete_cases": sum(item["complete_clear"] for item in values),
        "correct_absent_certificates": sum(
            item["absent_certificate_correct"] for item in values
        ),
    }
    metrics = (
        "virtual_time_s", "action_count", "measurement_count",
        "directional_probe_count", "failed_clear_remeasure_count",
        "failed_clear_count", "longest_consecutive_failed_clear_run",
        "max_failed_clears_for_one_source", "movement_distance_m",
        "cpu_wall_time_s", "long_clear_rescue_count",
        "long_clear_rescue_started_count",
        "long_clear_rescue_estimated_saving_s",
        "route_planning_call_count",
        "route_fallback_count",
    )
    for key in metrics:
        result[f"mean_{key}"] = statistics.fmean(
            item[key] for item in values
        )
    ordered = sorted(item["virtual_time_s"] for item in values)
    result["p90_virtual_time_s"] = ordered[
        max(0, math.ceil(0.9*len(ordered))-1)
    ]
    return result


def render_markdown(report):
    modes = tuple(report["modes"])
    lines = [
        "# Q4 长清除尾与多源路径规划配对消融",
        "",
        "> 本结果来自 FakeSimulator，不代表官方模拟器验收。",
        "",
        f"固定种子：`{report['seed']}`；场景数：{report['case_count']}。",
        "",
        "| 指标 | " + " | ".join(modes) + " |",
        "|---|" + "---:|"*len(modes),
    ]
    metrics = (
        ("完整清除", "complete_cases", ".0f"),
        ("正确无源证书", "correct_absent_certificates", ".0f"),
        ("平均虚拟时间/s", "mean_virtual_time_s", ".3f"),
        ("P90虚拟时间/s", "p90_virtual_time_s", ".3f"),
        ("平均动作数", "mean_action_count", ".3f"),
        ("平均检测数", "mean_measurement_count", ".3f"),
        ("平均失败清除数", "mean_failed_clear_count", ".3f"),
        ("平均最长连续失败清除", "mean_longest_consecutive_failed_clear_run", ".3f"),
        ("平均单源最大失败清除", "mean_max_failed_clears_for_one_source", ".3f"),
        ("平均移动距离/m", "mean_movement_distance_m", ".3f"),
        ("平均墙钟/s", "mean_cpu_wall_time_s", ".6f"),
        ("平均救援检查数", "mean_long_clear_rescue_count", ".3f"),
        ("平均救援启动数", "mean_long_clear_rescue_started_count", ".3f"),
        ("平均救援估计节省/s",
         "mean_long_clear_rescue_estimated_saving_s", ".3f"),
        ("平均路线调用数", "mean_route_planning_call_count", ".3f"),
        ("平均路线回退数", "mean_route_fallback_count", ".3f"),
    )
    for label, key, spec in metrics:
        values = [format(report["summaries"][mode][key], spec)
                  for mode in modes]
        lines.append(f"| {label} | " + " | ".join(values) + " |")
    if report["paired_wins_vs_baseline"]:
        lines.extend(["", "相对 baseline 的配对胜场："])
        for mode in modes:
            if mode == "baseline":
                continue
            lines.append(
                f"- `{mode}`：{report['paired_wins_vs_baseline'][mode]} / "
                f"{report['case_count']}"
            )
    lines.extend(["", "逐场参数与完整指标见同名 JSON。"])
    return "\n".join(lines)+"\n"


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=int, default=8)
    parser.add_argument("--seed", type=int, default=20269912)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument(
        "--modes", nargs="+", choices=tuple(MODES), default=list(MODES),
    )
    parser.add_argument("--max-actions", type=int, default=10000)
    parser.add_argument("--rolling-cpu-time-limit-s", type=float, default=3.0)
    parser.add_argument("--route-cpu-time-limit-s", type=float, default=0.25)
    parser.add_argument(
        "--output",
        default="output/q4_offline/long_tail_route_benchmark.json",
    )
    args = parser.parse_args(argv)
    if (args.cases < 1 or args.workers < 1 or args.max_actions < 1
            or args.rolling_cpu_time_limit_s <= 0.0
            or args.route_cpu_time_limit_s <= 0.0):
        parser.error("场景数、进程数、动作上限和CPU时限必须为正数。")
    cases = make_cases(args.cases, args.seed)
    rows_by_case = {
        case["case_index"]: {
            "case_index": case["case_index"], "sources": case["sources"],
        }
        for case in cases
    }
    jobs = [
        (case, mode, args.max_actions, args.rolling_cpu_time_limit_s,
         args.route_cpu_time_limit_s)
        for case in cases for mode in args.modes
    ]
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = [executor.submit(_run_job, job) for job in jobs]
        for future in as_completed(futures):
            case_index, mode, result = future.result()
            rows_by_case[case_index][mode] = result
            print(f"case={case_index} mode={mode} complete")
    rows = [rows_by_case[index] for index in sorted(rows_by_case)]
    summaries = {mode: summarize(rows, mode) for mode in args.modes}
    report = {
        "seed": args.seed,
        "case_count": args.cases,
        "workers": args.workers,
        "modes": args.modes,
        "max_actions": args.max_actions,
        "rolling_cpu_time_limit_s": args.rolling_cpu_time_limit_s,
        "route_cpu_time_limit_s": args.route_cpu_time_limit_s,
        "mode_config": MODES,
        "summaries": summaries,
        "paired_wins_vs_baseline": ({
            mode: sum(
                row[mode]["virtual_time_s"]
                < row["baseline"]["virtual_time_s"]
                for row in rows
            )
            for mode in args.modes if mode != "baseline"
        } if "baseline" in args.modes else {}),
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
