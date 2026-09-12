"""Paired offline benchmark for Q3 insertion + 2-opt source routing."""

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
from runtime.runner import run_policy
from sim.fake import FakeSimulator, FakeSource
from tests.q3.benchmark_adaptive import generate_cases


STRATEGIES = ("current", "insertion_2opt", "beam_cached")


class InstrumentedRoutePolicy(Q3Policy):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.action_modes = {}
        self.service_channels = {}
        self._route_record_by_request = {}

    def _action(self, state, kind, position=None, channel=None, mode=None):
        action = super()._action(state, kind, position, channel, mode)
        self.action_modes[action.request_id] = mode
        if kind in ("measure", "clear") and mode not in (
                "scan", "scan_batch"):
            service_channel = (
                state.batch_target_channel
                if mode == "joint_extra" and state.batch_target_channel
                else channel
            )
            self.service_channels[action.request_id] = service_channel
            if (self.route_planning_history
                    and mode in ("joint_target", "fallback_clear",
                                 "certified_clear")):
                record = self.route_planning_history[-1]
                if "request_id" not in record:
                    record["request_id"] = action.request_id
                    record["selected_service_channel"] = service_channel
                    self._route_record_by_request[action.request_id] = record
        return action

    def apply_response(self, state, action, response):
        previous_position = state.position
        previous_channel = state.current_channel
        if action.kind == "measure":
            realised = measure_cost(
                previous_position, action.position,
                previous_channel, action.channel,
            ).total_s
        elif action.kind == "clear":
            realised = clear_cost(
                previous_position, action.position,
                response.get("clear_result") == "success",
            ).total_s
        else:
            realised = 0.0
        super().apply_response(state, action, response)
        record = self._route_record_by_request.get(action.request_id)
        if record is not None:
            record["realised_next_action_cost_s"] = realised
            record["prediction_scope"] = (
                "predicted_first_block_vs_realised_next_action_only"
            )


def _policy(strategy, fim_limit_s, rolling_limit_s, route_limit_s,
            beam_route_limit_s, cache_capacity, beam_width,
            beam_max_expansions):
    return InstrumentedRoutePolicy(
        max_refinements=5,
        error_deg=1.005,
        fim_cpu_time_limit_s=fim_limit_s,
        adaptive_refinement=True,
        posterior_grid=True,
        joint_batch_mode="guaranteed",
        max_opportunistic_per_source=3,
        failed_clear_remeasure_mode="gated",
        rolling_time_mode="scenario",
        rolling_risk_metric="cvar",
        rolling_cpu_time_limit_s=rolling_limit_s,
        multi_source_route_mode=(
            strategy if strategy in ("insertion_2opt", "beam_cached")
            else "off"
        ),
        route_cpu_time_limit_s=(
            beam_route_limit_s if strategy == "beam_cached"
            else route_limit_s
        ),
        route_max_2opt_iterations=20,
        cache_capacity=cache_capacity,
        beam_width=beam_width,
        beam_max_expansions=beam_max_expansions,
    )


def _time_and_route_metrics(actions, action_modes, service_channels):
    position, channel = (0.0, 0.0), 1
    totals = Counter()
    service_order = []
    previous_service = None
    for entry in actions:
        action, response = entry["action"], entry["response"]
        kind = action["kind"]
        if kind not in ("measure", "clear"):
            continue
        point = (action["position"]["x"], action["position"]["y"])
        movement_m = math.dist(position, point)
        if kind == "measure":
            timing = measure_cost(position, point, channel, action["channel"])
            channel = action["channel"]
        else:
            timing = clear_cost(
                position, point,
                response["clear_result"] == "success",
            )
        mode = action_modes.get(action["request_id"])
        scan = mode in ("scan", "scan_batch")
        phase = "scan" if scan else "resolve"
        totals[f"{phase}_movement_distance_m"] += movement_m
        if not scan and movement_m >= 1000.0 - 1e-9:
            totals["resolve_long_jump_count"] += 1
            totals["resolve_long_jump_distance_m"] += movement_m
        service = service_channels.get(action["request_id"])
        if not scan and service is not None:
            if not service_order or service_order[-1] != service:
                service_order.append(service)
            if (previous_service is not None and service != previous_service
                    and movement_m > 1e-9):
                totals["cross_source_movement_distance_m"] += movement_m
            previous_service = service
        for field in ("movement_s", "switching_s", "measurement_s",
                      "optical_s", "laser_s"):
            totals[field] += getattr(timing, field)
        position = point
    totals["movement_distance_m"] = totals["movement_s"] * 5.0
    return dict(totals), service_order


def _run_one(task):
    (case, strategy, fim_limit_s, rolling_limit_s, route_limit_s,
     beam_route_limit_s, cache_capacity, beam_width,
     beam_max_expansions) = task
    policy = _policy(
        strategy, fim_limit_s, rolling_limit_s, route_limit_s,
        beam_route_limit_s, cache_capacity, beam_width,
        beam_max_expansions,
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
        totals, service_order = _time_and_route_metrics(
            summary.actions, policy.action_modes, policy.service_channels
        )
        route_times = [
            item.get("cpu_wall_time_s", 0.0)
            for item in policy.route_planning_history
        ]
        return {
            "case_id": case["case_id"],
            "strategy": strategy,
            "complete": summary.cleared_channels == expected,
            "cleared_channels": summary.cleared_channels,
            "expected_channels": expected,
            "virtual_time_s": summary.virtual_time_s,
            "action_count": len(summary.actions),
            "time_breakdown": totals,
            "actual_service_order": service_order,
            "route_planning_call_count": len(route_times),
            "route_planning_mean_wall_time_s": (
                statistics.fmean(route_times) if route_times else 0.0
            ),
            "route_planning_max_wall_time_s": (
                max(route_times) if route_times else 0.0
            ),
            "route_solver_status": dict(Counter(
                item.get("status", "unknown")
                for item in policy.route_planning_history
            )),
            "beam_expanded_nodes": sum(
                item.get("beam_expanded_nodes", 0)
                for item in policy.route_planning_history
            ),
            "cache_stats": policy.computation_cache.snapshot(),
            "route_plans": policy.route_planning_history,
            "cpu_wall_time_s": time.perf_counter() - started,
            "error": None,
        }
    except Exception as error:
        return {
            "case_id": case["case_id"],
            "strategy": strategy,
            "complete": False,
            "cleared_channels": [],
            "expected_channels": expected,
            "virtual_time_s": None,
            "action_count": None,
            "time_breakdown": {},
            "actual_service_order": [],
            "route_planning_call_count": len(policy.route_planning_history),
            "route_planning_mean_wall_time_s": None,
            "route_planning_max_wall_time_s": None,
            "route_solver_status": dict(Counter(
                item.get("status", "unknown")
                for item in policy.route_planning_history
            )),
            "beam_expanded_nodes": sum(
                item.get("beam_expanded_nodes", 0)
                for item in policy.route_planning_history
            ),
            "cache_stats": policy.computation_cache.snapshot(),
            "route_plans": policy.route_planning_history,
            "cpu_wall_time_s": time.perf_counter() - started,
            "error": f"{type(error).__name__}: {error}",
        }


def _p90(values):
    ordered = sorted(values)
    if not ordered:
        return None
    return ordered[max(0, math.ceil(0.9 * len(ordered)) - 1)]


def _summary(rows):
    completed = [row for row in rows if row["complete"]]
    values = [row["virtual_time_s"] for row in completed]
    result = {
        "completed_cases": len(completed),
        "case_count": len(rows),
        "mean_virtual_time_s": statistics.fmean(values) if values else None,
        "median_virtual_time_s": statistics.median(values) if values else None,
        "p90_virtual_time_s": _p90(values),
        "max_virtual_time_s": max(values) if values else None,
        "mean_action_count": (statistics.fmean(
            row["action_count"] for row in completed
        ) if completed else None),
        "mean_cpu_wall_time_s": statistics.fmean(
            row["cpu_wall_time_s"] for row in rows
        ),
    }
    for field in (
            "movement_distance_m", "scan_movement_distance_m",
            "resolve_movement_distance_m",
            "cross_source_movement_distance_m",
            "resolve_long_jump_count", "resolve_long_jump_distance_m",
            "movement_s", "switching_s", "measurement_s", "optical_s",
            "laser_s"):
        result[f"mean_{field}"] = (
            statistics.fmean(
                row["time_breakdown"].get(field, 0.0)
                for row in completed
            ) if completed else None
        )
    route_rows = [row for row in rows if row["route_planning_call_count"]]
    result["mean_route_planning_call_count"] = (
        statistics.fmean(row["route_planning_call_count"]
                         for row in route_rows)
        if route_rows else 0.0
    )
    result["mean_route_planning_wall_time_s"] = (
        statistics.fmean(row["route_planning_mean_wall_time_s"]
                         for row in route_rows)
        if route_rows else 0.0
    )
    result["max_route_planning_wall_time_s"] = (
        max(row["route_planning_max_wall_time_s"] for row in route_rows)
        if route_rows else 0.0
    )
    result["route_solver_status"] = dict(sum(
        (Counter(row["route_solver_status"]) for row in rows), Counter()
    ))
    result["mean_beam_expanded_nodes"] = statistics.fmean(
        row["beam_expanded_nodes"] for row in rows
    )
    cache_hits = sum(row["cache_stats"]["hits"] for row in rows)
    cache_misses = sum(row["cache_stats"]["misses"] for row in rows)
    result["cache_hits"] = cache_hits
    result["cache_misses"] = cache_misses
    result["cache_hit_rate"] = (
        cache_hits / (cache_hits + cache_misses)
        if cache_hits + cache_misses else 0.0
    )
    result["mean_cache_entries"] = statistics.fmean(
        row["cache_stats"]["entries"] for row in rows
    )
    return result


def _comparison(cases, rows, summaries):
    by_key = {(row["case_id"], row["strategy"]): row for row in rows}
    pairs = []
    for case in cases:
        current = by_key[(case["case_id"], "current")]
        route = by_key[(case["case_id"], "insertion_2opt")]
        both = current["complete"] and route["complete"]
        pair = {
            "case_id": case["case_id"],
            "both_complete": both,
            "current_error": current["error"],
            "insertion_2opt_error": route["error"],
        }
        for name, field in (
                ("virtual_time_s", None),
                ("resolve_movement_distance_m",
                 "resolve_movement_distance_m"),
                ("cross_source_movement_distance_m",
                 "cross_source_movement_distance_m"),
                ("long_jump_count", "resolve_long_jump_count"),
                ("long_jump_distance_m", "resolve_long_jump_distance_m"),
                ("cpu_wall_time_s", None)):
            if not both:
                delta = None
            elif field is None:
                delta = route[name] - current[name]
            else:
                delta = (route["time_breakdown"].get(field, 0.0)
                         - current["time_breakdown"].get(field, 0.0))
            pair[f"insertion_2opt_minus_current_{name}"] = delta
        pairs.append(pair)
    valid = [pair for pair in pairs if pair["both_complete"]]
    virtual_deltas = [
        pair["insertion_2opt_minus_current_virtual_time_s"]
        for pair in valid
    ]
    cross_deltas = [
        pair["insertion_2opt_minus_current_cross_source_movement_distance_m"]
        for pair in valid
    ]
    extra_incomplete = any(
        by_key[(case["case_id"], "current")]["complete"]
        and not by_key[(case["case_id"], "insertion_2opt")]["complete"]
        for case in cases
    )
    route_summary = summaries["insertion_2opt"]
    current_summary = summaries["current"]
    wins = sum(delta < -1e-9 for delta in virtual_deltas)
    return {
        "valid_pair_count": len(valid),
        "win_count": wins,
        "win_rate": wins / len(valid) if valid else None,
        "mean_virtual_time_delta_s": (
            statistics.fmean(virtual_deltas) if valid else None
        ),
        "mean_cross_source_movement_delta_m": (
            statistics.fmean(cross_deltas) if valid else None
        ),
        "has_extra_incomplete_case": extra_incomplete,
        "p90_not_worse": (
            route_summary["p90_virtual_time_s"]
            <= current_summary["p90_virtual_time_s"] + 1e-9
            if (route_summary["p90_virtual_time_s"] is not None
                and current_summary["p90_virtual_time_s"] is not None)
            else False
        ),
        "stable_material_cross_source_reduction_observed": (
            bool(valid)
            and statistics.fmean(cross_deltas) < -1e-9
            and sum(delta < -1e-9 for delta in cross_deltas) * 2
            >= len(cross_deltas)
        ),
        "pairs": pairs,
    }


def _pairwise_comparison(cases, rows, summaries, baseline, candidate):
    """Compare any candidate against a named baseline on identical cases."""
    by_key = {(row["case_id"], row["strategy"]): row for row in rows}
    pairs = []
    for case in cases:
        base = by_key[(case["case_id"], baseline)]
        proposed = by_key[(case["case_id"], candidate)]
        both = base["complete"] and proposed["complete"]
        pair = {"case_id": case["case_id"], "both_complete": both}
        for name, field in (
                ("virtual_time_s", None),
                ("resolve_movement_distance_m",
                 "resolve_movement_distance_m"),
                ("cross_source_movement_distance_m",
                 "cross_source_movement_distance_m"),
                ("long_jump_count", "resolve_long_jump_count"),
                ("cpu_wall_time_s", None)):
            if not both:
                delta = None
            elif field is None:
                delta = proposed[name] - base[name]
            else:
                delta = (proposed["time_breakdown"].get(field, 0.0)
                         - base["time_breakdown"].get(field, 0.0))
            pair[f"candidate_minus_baseline_{name}"] = delta
        pairs.append(pair)
    valid = [pair for pair in pairs if pair["both_complete"]]
    virtual = [
        pair["candidate_minus_baseline_virtual_time_s"] for pair in valid
    ]
    cross = [
        pair["candidate_minus_baseline_cross_source_movement_distance_m"]
        for pair in valid
    ]
    candidate_summary = summaries[candidate]
    baseline_summary = summaries[baseline]
    return {
        "baseline": baseline,
        "candidate": candidate,
        "valid_pair_count": len(valid),
        "win_count": sum(delta < -1e-9 for delta in virtual),
        "win_rate": (
            sum(delta < -1e-9 for delta in virtual) / len(valid)
            if valid else None
        ),
        "mean_virtual_time_delta_s": (
            statistics.fmean(virtual) if virtual else None
        ),
        "mean_cross_source_movement_delta_m": (
            statistics.fmean(cross) if cross else None
        ),
        "has_extra_incomplete_case": any(
            by_key[(case["case_id"], baseline)]["complete"]
            and not by_key[(case["case_id"], candidate)]["complete"]
            for case in cases
        ),
        "p90_not_worse": (
            candidate_summary["p90_virtual_time_s"]
            <= baseline_summary["p90_virtual_time_s"] + 1e-9
            if (candidate_summary["p90_virtual_time_s"] is not None
                and baseline_summary["p90_virtual_time_s"] is not None)
            else False
        ),
        "pairs": pairs,
    }


def _markdown(report):
    current = report["summaries"]["current"]
    route = report["summaries"]["insertion_2opt"]
    beam = report["summaries"]["beam_cached"]
    comparison = report["comparison"]
    beam_comparison = report["beam_comparison"]
    lines = [
        "# Q3 多源路线第二部分离线配对结果",
        "",
        "> 本结果只来自本地 FakeSimulator，不是官方模拟器成绩。",
        "",
        f"- 案例数：{report['case_count']}；种子：{report['seed']}",
        f"- FIM / 滚动 / 路线软截止：{report['fim_cpu_time_limit_s']} s / "
        f"{report['rolling_cpu_time_limit_s']} s / "
        f"{report['route_cpu_time_limit_s']} s",
        f"- 束搜索路线软截止：{report['beam_route_cpu_time_limit_s']} s；"
        f"束宽：{report['beam_width']}；最大扩展："
        f"{report['beam_max_expansions']}",
        "- 固定参数：error_deg=1.005，27 m 网格，顺便测量上限 3，"
        "CVaR，失败清除条件复测开启，最大动作数 5000",
        "",
        "| 指标 | current | insertion_2opt | beam_cached |",
        "|---|---:|---:|---:|",
    ]
    for label, key in (
            ("完成场景", "completed_cases"),
            ("平均总虚拟时间/s", "mean_virtual_time_s"),
            ("P90总虚拟时间/s", "p90_virtual_time_s"),
            ("最坏总虚拟时间/s", "max_virtual_time_s"),
            ("平均resolve移动/m", "mean_resolve_movement_distance_m"),
            ("平均跨源移动/m", "mean_cross_source_movement_distance_m"),
            ("平均长跳次数", "mean_resolve_long_jump_count"),
            ("平均长跳距离/m", "mean_resolve_long_jump_distance_m"),
            ("平均真实墙钟/s", "mean_cpu_wall_time_s")):
        lines.append(
            f"| {label} | {current[key]} | {route[key]} | {beam[key]} |"
        )
    lines.extend([
        "",
        f"- 胜场：{comparison['win_count']}/"
        f"{comparison['valid_pair_count']}，胜率 {comparison['win_rate']}",
        f"- 平均虚拟时间差（新-旧）："
        f"{comparison['mean_virtual_time_delta_s']} s",
        f"- 平均跨源移动差（新-旧）："
        f"{comparison['mean_cross_source_movement_delta_m']} m",
        f"- P90 未恶化：{comparison['p90_not_worse']}",
        f"- 新增未完成场景：{comparison['has_extra_incomplete_case']}",
        f"- 观察到稳定且有实际意义的跨源移动下降："
        f"{comparison['stable_material_cross_source_reduction_observed']}",
        f"- beam_cached 相对 insertion_2opt 胜场："
        f"{beam_comparison['win_count']}/"
        f"{beam_comparison['valid_pair_count']}，平均虚拟时间差："
        f"{beam_comparison['mean_virtual_time_delta_s']} s",
        f"- beam_cached 缓存命中率：{beam['cache_hit_rate']}；"
        f"平均束搜索扩展节点：{beam['mean_beam_expanded_nodes']}",
        "",
        "## 逐场差值",
        "",
        "| case | 总虚拟时间差/s | resolve移动差/m | 跨源移动差/m | 长跳次数差 |",
        "|---:|---:|---:|---:|---:|",
    ])
    for pair in comparison["pairs"]:
        lines.append(
            f"| {pair['case_id']} | "
            f"{pair['insertion_2opt_minus_current_virtual_time_s']} | "
            f"{pair['insertion_2opt_minus_current_resolve_movement_distance_m']} | "
            f"{pair['insertion_2opt_minus_current_cross_source_movement_distance_m']} | "
            f"{pair['insertion_2opt_minus_current_long_jump_count']} |"
        )
    lines.extend([
        "",
        "第二部分缓存和有限束搜索已实施；是否作为正式默认由用户决定。",
        "",
    ])
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Q3当前、插入2-opt与缓存束搜索三策略同场景配对"
    )
    parser.add_argument("--cases", type=int, default=4)
    parser.add_argument("--seed", type=int, default=20263912)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--fim-cpu-time-limit-s", type=float, default=10.0)
    parser.add_argument("--rolling-cpu-time-limit-s", type=float, default=3.0)
    parser.add_argument("--route-cpu-time-limit-s", type=float, default=0.25)
    parser.add_argument(
        "--beam-route-cpu-time-limit-s", type=float, default=1.0
    )
    parser.add_argument("--cache-capacity", type=int, default=4096)
    parser.add_argument("--beam-width", type=int, default=1)
    parser.add_argument("--beam-max-expansions", type=int, default=512)
    parser.add_argument(
        "--output", default="output/q3_offline/route_part2_benchmark.json"
    )
    args = parser.parse_args(argv)
    if (args.cases < 1 or args.workers < 1
            or args.fim_cpu_time_limit_s <= 0.0
            or args.rolling_cpu_time_limit_s <= 0.0
            or args.route_cpu_time_limit_s <= 0.0
            or args.beam_route_cpu_time_limit_s <= 0.0
            or args.cache_capacity < 1 or args.beam_width < 1
            or args.beam_max_expansions < 1):
        parser.error("案例数、进程数、容量、束参数和CPU时限必须为正数。")
    cases = generate_cases(args.cases, args.seed)
    tasks = [
        (case, strategy, args.fim_cpu_time_limit_s,
         args.rolling_cpu_time_limit_s, args.route_cpu_time_limit_s,
         args.beam_route_cpu_time_limit_s, args.cache_capacity,
         args.beam_width, args.beam_max_expansions)
        for case in cases for strategy in STRATEGIES
    ]
    started = time.perf_counter()
    if args.workers == 1:
        rows = [_run_one(task) for task in tasks]
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as executor:
            rows = list(executor.map(_run_one, tasks))
    summaries = {
        strategy: _summary([
            row for row in rows if row["strategy"] == strategy
        ]) for strategy in STRATEGIES
    }
    report = {
        "offline_only": True,
        "seed": args.seed,
        "case_count": args.cases,
        "sources_per_case": "uniform integer 10..16",
        "receive_radius_m": "uniform 1000..1500",
        "error_deg": 1.005,
        "clear_grid_spacing_m": 27.0,
        "max_opportunistic_per_source": 3,
        "failed_clear_remeasure_mode": "gated",
        "rolling_risk_metric": "cvar",
        "fim_cpu_time_limit_s": args.fim_cpu_time_limit_s,
        "rolling_cpu_time_limit_s": args.rolling_cpu_time_limit_s,
        "route_cpu_time_limit_s": args.route_cpu_time_limit_s,
        "beam_route_cpu_time_limit_s": args.beam_route_cpu_time_limit_s,
        "cache_capacity": args.cache_capacity,
        "beam_width": args.beam_width,
        "beam_max_expansions": args.beam_max_expansions,
        "max_actions": 5000,
        "benchmark_wall_time_s": time.perf_counter() - started,
        "cases": cases,
        "results": rows,
        "summaries": summaries,
    }
    report["comparison"] = _comparison(cases, rows, summaries)
    report["beam_comparison"] = _pairwise_comparison(
        cases, rows, summaries, "insertion_2opt", "beam_cached"
    )
    report["beam_vs_current"] = _pairwise_comparison(
        cases, rows, summaries, "current", "beam_cached"
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    markdown = output.with_suffix(".md")
    markdown.write_text(_markdown(report), encoding="utf-8")
    print(json.dumps({
        "summaries": summaries,
        "comparison": report["comparison"],
        "beam_comparison": report["beam_comparison"],
        "beam_vs_current": report["beam_vs_current"],
        "benchmark_wall_time_s": report["benchmark_wall_time_s"],
    }, ensure_ascii=False, indent=2))
    print(f"结果文件：{output}")
    print(f"摘要文件：{markdown}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
