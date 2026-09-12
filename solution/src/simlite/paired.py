"""simlite 成对比较框架（E1）：同池双臂对比 + 门1 判定。

基线臂 A 与候选臂 B 在完全相同的案例池（相同 seed 序列）上各跑一遍，
逐局给出明细与差值分布，并按门1 六条规则给出晋级判定。

口径说明：
- 每源测量次数：该源频道的 /measure 动作总数（扫描期 no_signal 探测 +
  resolve 期 refine 测量；absent 频道不计）。
- fallback 触发次数：mode=fallback_clear 的 /clear 动作数。
- clear 尝试/失败：全部 /clear 动作数 / 其中 clear_result!=success 数。
- 门1 a) 条：simlite 基线清除率已为 100%，故以"逐局 cleared 不降"为准；
  b) c+a==20；c) fallback+clear失败总量不升；d) 动作数<=max 且留>=30%
  裕量（即 <=0.7*max）；e) 总虚拟时间改进局>恶化局且中位改进>0，
  并报告逐局最坏恶化幅度；f) 全量测试与禁改区核验由收尾闭环执行。
"""

import json
import statistics

from .replay import run_episode

GATE_MAX_ACTIONS = 8000
GATE_ACTION_HEADROOM = 0.30  # 动作数须 <= max*(1-headroom)


def episode_stats(episode):
    """从 run_episode 输出汇总每源/fallback/clear 等计数。"""
    per_source_measure = {}
    fallback_count = 0
    clear_attempts = 0
    clear_failures = 0
    for entry in episode["actions"]:
        kind = entry["kind"]
        channel = entry.get("channel")
        if kind == "measure" and channel is not None:
            per_source_measure[channel] = per_source_measure.get(channel, 0) + 1
        elif kind == "clear":
            clear_attempts += 1
            if entry.get("mode") == "fallback_clear":
                fallback_count += 1
            if entry.get("response", {}).get("clear_result") != "success":
                clear_failures += 1
    counts = [count for channel, count in sorted(per_source_measure.items())
              if channel in set(episode["cleared_channels"])]
    return {
        "cleared": episode["cleared_count"],
        "absent": episode["absent_count"],
        "combined": episode["cleared_count"] + episode["absent_count"],
        "virtual_time_s": episode["virtual_time_s"],
        "scan_s": episode["breakdown"]["scan_s"],
        "resolve_s": episode["breakdown"]["resolve_s"],
        "clear_action_s": episode["breakdown"]["clear_action_s"],
        "actions": episode["action_count"],
        "fallback_count": fallback_count,
        "clear_attempts": clear_attempts,
        "clear_failures": clear_failures,
        "per_source_measure": counts,
        "per_source_measure_mean": (statistics.fmean(counts)
                                    if counts else 0.0),
    }


def _difference(a, b):
    return round(b - a, 6)


def paired_compare(factory_a, factory_b, seeds, *, workers=1,
                   max_actions=GATE_MAX_ACTIONS):
    """同池成对对比。seeds 为每个案例的独立种子（列表）。

    每个 seed 先跑基线臂再跑候选臂：同 seed 内 A/B 相邻执行，使两臂的
    CPU 竞争与缓存环境尽可能一致，逐局差值更可信。
    """
    if workers == 1:
        pairs = [_run_pair(factory_a, factory_b, seed, max_actions)
                 for seed in seeds]
    else:
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(max_workers=workers) as executor:
            pairs = list(executor.map(
                _run_pair, [factory_a] * len(seeds), [factory_b] * len(seeds),
                seeds, [max_actions] * len(seeds)))
    runs_a = [pair[0] for pair in pairs]
    runs_b = [pair[1] for pair in pairs]
    rows = []
    for seed, a, b in zip(seeds, runs_a, runs_b):
        rows.append({
            "seed": seed,
            "a": episode_stats(a),
            "b": episode_stats(b),
        })
    return {"rows": rows, "summary": summarize_paired(rows),
            "gate": gate_verdict(rows, max_actions=max_actions)}


def _run_pair(factory_a, factory_b, seed, max_actions):
    return (_run_one(factory_a, seed, max_actions),
            _run_one(factory_b, seed, max_actions))


def _run_one(factory, seed, max_actions):
    import random
    from . import Simulator, generate_sources

    rng = random.Random(seed)
    sources = generate_sources(rng, direction_ratio=0.0)
    simulator = Simulator(sources, error_bound_deg=1.0)
    episode = run_episode(factory(), simulator, max_actions=max_actions)
    episode["official_count_generated"] = len(sources)
    episode["case_seed"] = seed
    return episode


def _pair_series(rows, key):
    return [(row["a"][key], row["b"][key]) for row in rows]


def summarize_paired(rows):
    def series_stats(values):
        if not values:
            return {"mean": None, "median": None, "p90": None, "min": None,
                    "max": None}
        ordered = sorted(values)
        p90 = ordered[min(len(ordered) - 1, int(round(0.9 * (len(ordered) - 1))))]
        return {"mean": statistics.fmean(values),
                "median": statistics.median(values),
                "p90": p90, "min": min(values), "max": max(values)}

    result = {"episode_count": len(rows)}
    for key, label in (
        ("virtual_time_s", "总虚拟时间"),
        ("scan_s", "扫描段"),
        ("resolve_s", "resolve 段"),
        ("clear_action_s", "清除动作段"),
        ("actions", "动作数"),
        ("fallback_count", "fallback 次数"),
        ("clear_failures", "clear 失败次数"),
        ("clear_attempts", "clear 尝试次数"),
        ("per_source_measure_mean", "每源平均测量次数"),
    ):
        diffs = [row["b"][key] - row["a"][key] for row in rows]
        result[key] = {
            "a": series_stats([row["a"][key] for row in rows]),
            "b": series_stats([row["b"][key] for row in rows]),
            "difference": series_stats(diffs),
            "b_better": sum(value < -1e-9 for value in diffs),
            "tie": sum(abs(value) <= 1e-9 for value in diffs),
            "b_worse": sum(value > 1e-9 for value in diffs),
            "max_b_minus_a": max(diffs) if diffs else None,
            "label": label,
        }
    return result


def gate_verdict(rows, max_actions=GATE_MAX_ACTIONS):
    """门1 六条判定；返回 {规则: {pass, detail}}。"""
    cleared_diffs = [row["b"]["cleared"] - row["a"]["cleared"]
                     for row in rows]
    combined = [row["b"]["combined"] for row in rows]
    fallback_diffs = [row["b"]["fallback_count"] + row["b"]["clear_failures"]
                      - row["a"]["fallback_count"] - row["a"]["clear_failures"]
                      for row in rows]
    action_max = max(row["b"]["actions"] for row in rows)
    time_diffs = [row["b"]["virtual_time_s"] - row["a"]["virtual_time_s"]
                  for row in rows]
    verdict = {
        "a_cleared_not_lower": {
            "pass": all(value >= 0 for value in cleared_diffs),
            "detail": "逐局 cleared 差值：" + ",".join(
                str(value) for value in cleared_diffs),
        },
        "b_full_certificate": {
            "pass": all(value == 20 for value in combined),
            "detail": "b 臂 c+a 全部为 20",
        },
        "c_fallback_and_clear_failures_not_up": {
            "pass": sum(value > 0 for value in fallback_diffs) == 0,
            "detail": "逐局(fallback+clear失败)差："
                      + ",".join(str(value) for value in fallback_diffs),
        },
        "d_action_headroom": {
            "pass": action_max <= (1 - GATE_ACTION_HEADROOM) * max_actions,
            "detail": f"b 臂最大动作数 {action_max} / 上限 {max_actions} "
                      f"（要求 <={int((1 - GATE_ACTION_HEADROOM) * max_actions)}）",
        },
        "e_time_improvement": {
            "pass": (sum(value < -1e-9 for value in time_diffs) >
                     sum(value > 1e-9 for value in time_diffs)
                     and statistics.median(time_diffs) < 0),
            "detail": {
                "b_better": sum(value < -1e-9 for value in time_diffs),
                "b_worse": sum(value > 1e-9 for value in time_diffs),
                "ties": sum(abs(value) <= 1e-9 for value in time_diffs),
                "median_difference_s": statistics.median(time_diffs),
                "worst_worsening_s": max((value for value in time_diffs
                                          if value > 0), default=0.0),
            },
        },
    }
    verdict["overall_pass"] = all(item["pass"] for item in verdict.values())
    return verdict


def write_paired_report(payload, path):
    """落盘成对对比 JSON 证据；顶层含 summary 与 gate。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    return path


__all__ = ["episode_stats", "paired_compare", "gate_verdict",
           "summarize_paired", "write_paired_report"]