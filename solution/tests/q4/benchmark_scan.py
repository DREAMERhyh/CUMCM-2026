"""Paired discovery-scan benchmark for the 121- and 37-point Q4 covers."""

import argparse
import json
import math
from pathlib import Path
import random
import statistics
import sys
import time

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from q4.policy import Q4Policy
from sim.fake import FakeSimulator, FakeSource


class DiscoveryOnlyQ4Policy(Q4Policy):
    def _resolve_action(self, state, *, allow_exit=True):
        state.phase = "exit"
        return None


def make_cases(count, seed):
    rng = random.Random(seed)
    cases = []
    for case_index in range(count):
        source_count = rng.randint(10, 16)
        channels = sorted(rng.sample(range(1, 21), source_count))
        sources = []
        for item_index, channel in enumerate(channels):
            radius = 1800.0*math.sqrt(rng.random())
            angle = 2.0*math.pi*rng.random()
            position = radius*math.cos(angle), radius*math.sin(angle)
            directional = (item_index+case_index) % 2 == 0
            sources.append({
                "channel": channel,
                "position": position,
                "receive_radius": rng.uniform(1000.0, 1500.0),
                "direction_deg": (
                    rng.uniform(0.0, 360.0) if directional else None
                ),
            })
        cases.append({"case_index": case_index, "sources": sources})
    return cases


def run_case(case, scan_mode):
    client = FakeSimulator([
        FakeSource(
            item["channel"], tuple(item["position"]),
            item["receive_radius"], item["direction_deg"],
        )
        for item in case["sources"]
    ])
    policy = DiscoveryOnlyQ4Policy(
        max_refinements=0, scan_mode=scan_mode,
    )
    state = policy.initial_state()
    actions = []
    started = time.perf_counter()
    while len(actions) < 3000:
        action = policy.next_action(state)
        if action.kind == "exit":
            break
        response = client.execute(action)
        actions.append(action)
        policy.apply_response(state, action, response)
    else:
        raise RuntimeError("Q4扫描对拍达到动作上限。")

    source_channels = {item["channel"] for item in case["sources"]}
    discovered = set(state.sources) | state.cleared
    measured = [item for item in actions if item.kind == "measure"]
    position = (0.0, 0.0)
    movement_m = 0.0
    for action in measured:
        movement_m += math.dist(position, action.position)
        position = tuple(action.position)
    return {
        "scan_mode": scan_mode,
        "coverage_point_count": len(policy.coverage_points),
        "action_count": len(actions),
        "measurement_count": len(measured),
        "movement_distance_m": movement_m,
        "virtual_time_s": state.virtual_time_s,
        "cpu_wall_time_s": time.perf_counter()-started,
        "source_count": len(source_channels),
        "discovered_count": len(discovered & source_channels),
        "complete_discovery": source_channels <= discovered,
        "absent_certificate_correct": (
            state.absent == set(range(1, 21))-source_channels
        ),
    }


def summarize(rows, mode):
    selected = [item[mode] for item in rows]
    return {
        "complete_cases": sum(item["complete_discovery"] for item in selected),
        "correct_absent_certificates": sum(
            item["absent_certificate_correct"] for item in selected
        ),
        "mean_measurement_count": statistics.fmean(
            item["measurement_count"] for item in selected
        ),
        "mean_movement_distance_m": statistics.fmean(
            item["movement_distance_m"] for item in selected
        ),
        "mean_virtual_time_s": statistics.fmean(
            item["virtual_time_s"] for item in selected
        ),
        "max_virtual_time_s": max(item["virtual_time_s"] for item in selected),
        "mean_cpu_wall_time_s": statistics.fmean(
            item["cpu_wall_time_s"] for item in selected
        ),
    }


def markdown(report):
    count = report["case_count"]
    lines = [
        "# Q4 全局扫描 121 点与 37 点同场景配对",
        "",
        "> 本结果来自本地规则替身，只比较发现扫描，不代表官方模拟器验收。",
        "",
        f"固定种子：`{report['seed']}`；混合全向/定向场景数：{count}。",
        "",
        "| 指标 | grid121 | triangular37 |",
        "|---|---:|---:|",
    ]
    left = report["summaries"]["grid121"]
    right = report["summaries"]["triangular37"]
    metrics = (
        ("完整发现", "complete_cases", ".0f"),
        ("正确无源证书", "correct_absent_certificates", ".0f"),
        ("平均检测数", "mean_measurement_count", ".3f"),
        ("平均移动距离/m", "mean_movement_distance_m", ".3f"),
        ("平均虚拟时间/s", "mean_virtual_time_s", ".3f"),
        ("最坏虚拟时间/s", "max_virtual_time_s", ".3f"),
        ("平均真实墙钟/s", "mean_cpu_wall_time_s", ".6f"),
    )
    for label, key, spec in metrics:
        lines.append(
            f"| {label} | {format(left[key], spec)} | {format(right[key], spec)} |"
        )
    reduction = report["virtual_time_reduction_ratio"]*100.0
    lines.extend([
        "",
        f"37 点方案平均扫描虚拟时间变化：{reduction:.3f}%。",
        "完整逐场结果见同名 JSON。",
    ])
    return "\n".join(lines)+"\n"


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=int, default=8)
    parser.add_argument("--seed", type=int, default=20265912)
    parser.add_argument(
        "--output", default="output/q4_offline/scan_benchmark.json",
    )
    args = parser.parse_args(argv)
    if args.cases < 1:
        parser.error("--cases 至少为1。")

    cases = make_cases(args.cases, args.seed)
    rows = []
    for case in cases:
        rows.append({
            "case_index": case["case_index"],
            "sources": case["sources"],
            "grid121": run_case(case, "grid121"),
            "triangular37": run_case(case, "triangular37"),
        })
    summaries = {
        mode: summarize(rows, mode)
        for mode in ("grid121", "triangular37")
    }
    baseline = summaries["grid121"]["mean_virtual_time_s"]
    candidate = summaries["triangular37"]["mean_virtual_time_s"]
    report = {
        "seed": args.seed,
        "case_count": args.cases,
        "scope": "discovery_scan_only",
        "summaries": summaries,
        "virtual_time_reduction_ratio": (baseline-candidate)/baseline,
        "rows": rows,
    }
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    path.with_suffix(".md").write_text(markdown(report), encoding="utf-8")
    print(markdown(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
