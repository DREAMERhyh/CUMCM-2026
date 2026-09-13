"""Paired Q4 benchmark for optional Q2/FIM/Pareto probe candidates."""

import argparse
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
    "off": "off",
    "hybrid_pareto": "hybrid_pareto",
}


def run_case(case, mode, max_actions, rolling_limit_s,
             integrated_limit_s, fim_limit_s, route_limit_s):
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
        q2_version="new",
        failed_clear_remeasure_mode="gated",
        directional_rolling_mode="scenario",
        directional_rolling_risk_metric="cvar",
        directional_rolling_cpu_time_limit_s=rolling_limit_s,
        q2_candidate_mode=MODES[mode],
        q2_candidate_fim_cpu_time_limit_s=fim_limit_s,
        integrated_planning_cpu_time_limit_s=integrated_limit_s,
        long_clear_tail_mode="adaptive",
        multi_source_route_mode="insertion_2opt",
        route_cpu_time_limit_s=route_limit_s,
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
        raise RuntimeError("Q4候选接入对拍达到动作上限仍未退出。")
    elapsed = time.perf_counter()-started
    source_channels = {item["channel"] for item in case["sources"]}
    movement_m = 0.0
    position = (0.0, 0.0)
    for action, _, _ in records:
        if action.position is not None:
            movement_m += math.dist(position, action.position)
            position = tuple(action.position)

    planning = [
        item for item in state.probe_diagnostics
        if item.get("event") == "q2_candidate_planning"
    ]
    q2_selected = [
        item for item in state.rolling_diagnostics
        if (item.get("decision") == "measure"
            and item.get("candidate_source", "certified") != "certified")
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
        "failed_clear_count": sum(
            response.get("clear_result") == "no_target_in_range"
            for _, response, _ in records
        ),
        "movement_distance_m": movement_m,
        "virtual_time_s": state.virtual_time_s,
        "cpu_wall_time_s": elapsed,
        "q2_candidate_planning_count": len(planning),
        "q2_candidate_cache_hit_count": sum(
            item.get("cache_hit", False) for item in planning
        ),
        "q2_candidate_extra_point_count": sum(
            item.get("extra_point_count", 0) for item in planning
        ),
        "q2_candidate_selected_count": len(q2_selected),
        "q2_candidate_planning_wall_time_s": sum(
            item.get("cpu_wall_time_s", 0.0) for item in planning
        ),
        "rolling_wall_time_s": sum(
            item.get("cpu_wall_time_s", 0.0)
            for item in state.rolling_diagnostics
        ),
        "rolling_fallback_count": sum(
            item.get("solver_status") == "fallback"
            for item in state.rolling_diagnostics
        ),
        "q4_pareto_decision_count": sum(
            bool(item.get("q4_pareto_front"))
            for item in state.rolling_diagnostics
        ),
        "cache": policy.computation_cache.snapshot(),
    }


def _run_job(job):
    case, mode, max_actions, rolling, integrated, fim, route = job
    return case["case_index"], mode, run_case(
        case, mode, max_actions, rolling, integrated, fim, route,
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
        "directional_probe_count", "failed_clear_count",
        "movement_distance_m", "cpu_wall_time_s",
        "q2_candidate_planning_count", "q2_candidate_cache_hit_count",
        "q2_candidate_extra_point_count", "q2_candidate_selected_count",
        "q2_candidate_planning_wall_time_s", "rolling_wall_time_s",
        "rolling_fallback_count", "q4_pareto_decision_count",
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
    summaries = report["summaries"]
    lines = [
        "# Q4 接入 Q2/FIM/Pareto 候选配对",
        "",
        "> 本结果来自 FakeSimulator，不代表官方模拟器验收。",
        "",
        f"固定种子：`{report['seed']}`；场景数：{report['case_count']}。",
        "",
        "| 指标 | off | hybrid_pareto |",
        "|---|---:|---:|",
    ]
    metrics = (
        ("完整清除", "complete_cases", ".0f"),
        ("正确无源证书", "correct_absent_certificates", ".0f"),
        ("平均虚拟时间/s", "mean_virtual_time_s", ".3f"),
        ("P90虚拟时间/s", "p90_virtual_time_s", ".3f"),
        ("平均动作数", "mean_action_count", ".3f"),
        ("平均检测数", "mean_measurement_count", ".3f"),
        ("平均失败清除", "mean_failed_clear_count", ".3f"),
        ("平均移动/m", "mean_movement_distance_m", ".3f"),
        ("平均墙钟/s", "mean_cpu_wall_time_s", ".6f"),
        ("平均Q2候选规划次数", "mean_q2_candidate_planning_count", ".3f"),
        ("平均Q2候选被选次数", "mean_q2_candidate_selected_count", ".3f"),
        ("平均候选规划墙钟/s",
         "mean_q2_candidate_planning_wall_time_s", ".6f"),
        ("平均方向评价回退", "mean_rolling_fallback_count", ".3f"),
    )
    for label, key, spec in metrics:
        lines.append(
            f"| {label} | {summaries['off'][key]:{spec}} | "
            f"{summaries['hybrid_pareto'][key]:{spec}} |"
        )
    lines.extend([
        "",
        f"hybrid_pareto 成对更快：{report['paired_wins']} / "
        f"{report['case_count']}。",
        f"建议默认启用：`{str(report['recommend_default_on']).lower()}`。",
        "",
        "逐场源参数和完整指标见同名 JSON。",
    ])
    return "\n".join(lines)+"\n"


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=int, default=8)
    parser.add_argument("--seed", type=int, default=20270913)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--max-actions", type=int, default=10000)
    parser.add_argument("--rolling-cpu-time-limit-s", type=float, default=3.0)
    parser.add_argument(
        "--integrated-planning-cpu-time-limit-s", type=float, default=3.0,
    )
    parser.add_argument(
        "--q2-candidate-fim-cpu-time-limit-s", type=float, default=0.75,
    )
    parser.add_argument("--route-cpu-time-limit-s", type=float, default=3.0)
    parser.add_argument(
        "--output", default="output/q4_offline/q2_candidate_benchmark.json",
    )
    args = parser.parse_args(argv)
    if (args.cases < 1 or args.workers < 1 or args.max_actions < 1
            or args.rolling_cpu_time_limit_s <= 0.0
            or args.integrated_planning_cpu_time_limit_s <= 0.0
            or args.q2_candidate_fim_cpu_time_limit_s <= 0.0
            or args.route_cpu_time_limit_s <= 0.0):
        parser.error("场景数、进程数、动作上限和各计算时限必须为正数。")

    cases = make_cases(args.cases, args.seed)
    rows_by_case = {
        case["case_index"]: {
            "case_index": case["case_index"], "sources": case["sources"],
        }
        for case in cases
    }
    jobs = [
        (case, mode, args.max_actions, args.rolling_cpu_time_limit_s,
         args.integrated_planning_cpu_time_limit_s,
         args.q2_candidate_fim_cpu_time_limit_s,
         args.route_cpu_time_limit_s)
        for case in cases for mode in MODES
    ]
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = [executor.submit(_run_job, job) for job in jobs]
        for future in as_completed(futures):
            case_index, mode, result = future.result()
            rows_by_case[case_index][mode] = result
    rows = [rows_by_case[index] for index in sorted(rows_by_case)]
    summaries = {mode: summarize(rows, mode) for mode in MODES}
    paired_wins = sum(
        row["hybrid_pareto"]["virtual_time_s"]
        < row["off"]["virtual_time_s"]-1e-9
        for row in rows
    )
    safe = all(
        summaries[mode]["complete_cases"] == args.cases
        and summaries[mode]["correct_absent_certificates"] == args.cases
        for mode in MODES
    )
    recommend = (
        safe
        and summaries["hybrid_pareto"]["mean_virtual_time_s"]
        < summaries["off"]["mean_virtual_time_s"]
    )
    report = {
        "seed": args.seed,
        "case_count": args.cases,
        "configuration": vars(args),
        "summaries": summaries,
        "paired_wins": paired_wins,
        "acceptance_rule": (
            "all cases safe and mean virtual time is lower; wall time, P90, "
            "paired wins and failed clears are reported but do not affect "
            "enabling"
        ),
        "recommend_default_on": recommend,
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
