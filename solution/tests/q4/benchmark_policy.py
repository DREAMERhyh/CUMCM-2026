"""Paired end-to-end Q4 benchmark for the two certified scan covers."""

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
from runtime.runner import run_policy
from sim.fake import FakeSimulator, FakeSource
from tests.q4.benchmark_scan import make_cases


def run_case(case, scan_mode, max_actions):
    client = FakeSimulator([
        FakeSource(
            item["channel"], tuple(item["position"]),
            item["receive_radius"], item["direction_deg"],
        )
        for item in case["sources"]
    ])
    policy = Q4Policy(max_refinements=2, scan_mode=scan_mode)
    started = time.perf_counter()
    summary = run_policy(policy, client, max_actions=max_actions)
    elapsed = time.perf_counter()-started
    source_channels = {item["channel"] for item in case["sources"]}
    actions = [item["action"] for item in summary.actions]
    measurements = [item for item in actions if item["kind"] == "measure"]
    clears = [
        item for item in summary.actions if item["action"]["kind"] == "clear"
    ]
    movement_m = 0.0
    position = (0.0, 0.0)
    for action in actions:
        encoded = action.get("position")
        if encoded is None:
            continue
        point = encoded["x"], encoded["y"]
        movement_m += math.dist(position, point)
        position = point
    return {
        "scan_mode": scan_mode,
        "source_count": len(source_channels),
        "cleared_count": len(summary.cleared_channels),
        "complete_clear": set(summary.cleared_channels) == source_channels,
        "absent_certificate_correct": (
            set(summary.absent_channels) == set(range(1, 21))-source_channels
        ),
        "action_count": len(actions),
        "measurement_count": len(measurements),
        "clear_count": len(clears),
        "failed_clear_count": sum(
            item["response"].get("clear_result") == "no_target_in_range"
            for item in clears
        ),
        "movement_distance_m": movement_m,
        "virtual_time_s": summary.virtual_time_s,
        "cpu_wall_time_s": elapsed,
    }


def summarize(rows, mode):
    selected = [item[mode] for item in rows]
    return {
        "complete_cases": sum(item["complete_clear"] for item in selected),
        "correct_absent_certificates": sum(
            item["absent_certificate_correct"] for item in selected
        ),
        "mean_virtual_time_s": statistics.fmean(
            item["virtual_time_s"] for item in selected
        ),
        "median_virtual_time_s": statistics.median(
            item["virtual_time_s"] for item in selected
        ),
        "max_virtual_time_s": max(item["virtual_time_s"] for item in selected),
        "mean_action_count": statistics.fmean(
            item["action_count"] for item in selected
        ),
        "mean_measurement_count": statistics.fmean(
            item["measurement_count"] for item in selected
        ),
        "mean_failed_clear_count": statistics.fmean(
            item["failed_clear_count"] for item in selected
        ),
        "mean_movement_distance_m": statistics.fmean(
            item["movement_distance_m"] for item in selected
        ),
        "mean_cpu_wall_time_s": statistics.fmean(
            item["cpu_wall_time_s"] for item in selected
        ),
    }


def render_markdown(report):
    left = report["summaries"]["grid121"]
    right = report["summaries"]["triangular37"]
    lines = [
        "# Q4 完整策略 121 点与 37 点同场景配对",
        "",
        "> 本结果来自本地规则替身，不代表官方模拟器验收。",
        "",
        f"固定种子：`{report['seed']}`；场景数：{report['case_count']}。",
        "每种场景包含 10-16 个全向/定向混合源，两方案使用完全相同的源。",
        "",
        "| 指标 | grid121 | triangular37 |",
        "|---|---:|---:|",
    ]
    metrics = (
        ("完整清除", "complete_cases", ".0f"),
        ("正确无源证书", "correct_absent_certificates", ".0f"),
        ("平均虚拟时间/s", "mean_virtual_time_s", ".3f"),
        ("中位虚拟时间/s", "median_virtual_time_s", ".3f"),
        ("最坏虚拟时间/s", "max_virtual_time_s", ".3f"),
        ("平均动作数", "mean_action_count", ".3f"),
        ("平均检测数", "mean_measurement_count", ".3f"),
        ("平均失败清除数", "mean_failed_clear_count", ".3f"),
        ("平均移动距离/m", "mean_movement_distance_m", ".3f"),
        ("平均真实墙钟/s", "mean_cpu_wall_time_s", ".6f"),
    )
    for label, key, spec in metrics:
        lines.append(
            f"| {label} | {format(left[key], spec)} | {format(right[key], spec)} |"
        )
    reduction = report["virtual_time_reduction_ratio"]*100.0
    wins = report["triangular37_wins"]
    lines.extend([
        "",
        f"triangular37 成对更快：{wins}/{report['case_count']}；"
        f"平均虚拟时间减少 {reduction:.3f}%。",
        "完整逐场数据和源参数见同名 JSON。",
    ])
    return "\n".join(lines)+"\n"


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=int, default=8)
    parser.add_argument("--seed", type=int, default=20266912)
    parser.add_argument("--max-actions", type=int, default=10000)
    parser.add_argument(
        "--output", default="output/q4_offline/policy_benchmark.json",
    )
    args = parser.parse_args(argv)
    if args.cases < 1 or args.max_actions < 1:
        parser.error("场景数和动作上限必须为正数。")

    cases = make_cases(args.cases, args.seed)
    rows = []
    for case in cases:
        rows.append({
            "case_index": case["case_index"],
            "sources": case["sources"],
            "grid121": run_case(case, "grid121", args.max_actions),
            "triangular37": run_case(
                case, "triangular37", args.max_actions,
            ),
        })
    summaries = {
        mode: summarize(rows, mode)
        for mode in ("grid121", "triangular37")
    }
    old = summaries["grid121"]["mean_virtual_time_s"]
    new = summaries["triangular37"]["mean_virtual_time_s"]
    report = {
        "seed": args.seed,
        "case_count": args.cases,
        "max_actions": args.max_actions,
        "summaries": summaries,
        "triangular37_wins": sum(
            item["triangular37"]["virtual_time_s"]
            < item["grid121"]["virtual_time_s"]
            for item in rows
        ),
        "virtual_time_reduction_ratio": (old-new)/old,
        "rows": rows,
    }
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    text = render_markdown(report)
    path.with_suffix(".md").write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
