"""simlite 批量回放：策略端到端一局/多局的统计与时间对账。

与 ``runtime.runner`` 的差异：本模块直调策略状态机与 simlite 模拟器
（无 HTTP、无 run_live_policy 的现实时限逻辑），并额外输出
扫描/resolve/清除动作三类虚拟时间拆分，以及用 ``common/time_model``
逐动作重算与模拟器官方时刻的对账结果。
"""

from collections import Counter
import json
import math
import random
import time

from common.time_model import clear_cost, measure_cost

from . import Simulator, generate_sources

MAX_ACTIONS = 10_000
ACCOUNTING_TOLERANCE = 1e-3  # 官方微秒整数累计 vs 浮点重算的容许差（秒）


def run_episode(policy, simulator, *, max_actions=MAX_ACTIONS):
    """跑完一局，返回统计字典（多个字段供批量回放与对账使用）。"""
    if max_actions < 2:
        raise ValueError("max_actions 至少为 2。")
    state = policy.initial_state()
    breakdown = {
        "scan_s": 0.0,
        "resolve_s": 0.0,
        "clear_action_s": 0.0,
        "measure_action_s": 0.0,
        "enter_exit_s": 0.0,
    }
    recon = {"movement_s": 0.0, "switching_s": 0.0, "measurement_s": 0.0,
             "optical_s": 0.0, "laser_s": 0.0}
    previous_position = (0.0, 0.0)
    previous_channel = 1
    action_log = []
    virtual_prev = 0.0
    for _ in range(max_actions):
        action = policy.next_action(state)
        action_mode = getattr(state, "pending_mode", None)
        response = simulator.execute(action)
        delta = response["virtual_time_s"] - virtual_prev
        virtual_prev = response["virtual_time_s"]
        phase = getattr(state, "phase", None)
        if action.kind == "measure":
            timing = measure_cost(previous_position, action.position,
                                  previous_channel, action.channel)
            for key in ("movement_s", "switching_s", "measurement_s"):
                recon[key] += getattr(timing, key)
            previous_position = action.position
            previous_channel = action.channel
            breakdown["measure_action_s"] += delta
            if phase == "scan":
                breakdown["scan_s"] += delta
            else:
                breakdown["resolve_s"] += delta
        elif action.kind == "clear":
            timing = clear_cost(previous_position, action.position,
                                response.get("clear_result") == "success")
            for key in ("movement_s", "optical_s", "laser_s"):
                recon[key] += getattr(timing, key)
            previous_position = action.position
            breakdown["clear_action_s"] += delta
            breakdown["resolve_s"] += delta
        else:
            breakdown["enter_exit_s"] += delta
        action_log.append({
            "kind": action.kind,
            "position": list(action.position) if action.position else None,
            "channel": action.channel,
            "request_id": action.request_id,
            "mode": action_mode,
            "phase": phase,
            "virtual_time_s": response["virtual_time_s"],
            "delta_s": delta,
            "response": {key: value for key, value in response.items()
                         if key != "real_timestamp_ms"},
        })
        policy.apply_response(state, action, response)
        if action.kind == "exit" and response.get("accepted") is True:
            break
    else:
        raise RuntimeError("达到动作上限，策略未终止。")

    recon_total = sum(recon.values())
    cleared_count = len(getattr(state, "cleared", set()))
    total = virtual_prev
    accounting_ok = abs(recon_total - total) <= ACCOUNTING_TOLERANCE
    return {
        "cleared_channels": sorted(getattr(state, "cleared", set())),
        "cleared_count": cleared_count,
        "absent_channels": sorted(getattr(state, "absent", set())),
        "absent_count": len(getattr(state, "absent", set())),
        "total_sources_confirmed": (
            len(getattr(state, "cleared", set()))
            + len(getattr(state, "absent", set()))
        ),
        "virtual_time_s": total,
        "average_clear_time_s": (total / cleared_count
                                 if cleared_count else None),
        "breakdown": breakdown,
        "recon": {"recon_total_s": recon_total,
                  "official_total_s": total,
                  "difference_s": recon_total - total,
                  "accounting_ok": accounting_ok,
                  "per_component_s": dict(recon)},
        "action_count": len(action_log),
        "actions": action_log,
    }


def replay_batch(make_policy, count, *, seed, workers=1,
                 direction_ratio=0.0, max_actions=MAX_ACTIONS):
    """并行回放 ``count`` 局，返回每局统计列表与汇总。"""
    if count < 1 or workers < 1:
        raise ValueError("count 与 workers 必须为正整数。")
    if workers == 1:
        episodes = [_one_episode(make_policy, seed + index,
                                 direction_ratio, max_actions)
                    for index in range(count)]
    else:
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(max_workers=workers) as executor:
            episodes = list(executor.map(
                _one_episode, [make_policy]*count,
                [seed + index for index in range(count)],
                [direction_ratio]*count, [max_actions]*count,
            ))
    summary = summarize_episodes(episodes, seed=seed)
    return dict(episodes=episodes, summary=summary)


def _one_episode(make_policy, episode_seed, direction_ratio, max_actions):
    rng = random.Random(episode_seed)
    sources = generate_sources(rng, direction_ratio=direction_ratio)
    simulator = Simulator(sources, error_bound_deg=1.0)
    episode = run_episode(make_policy(), simulator, max_actions=max_actions)
    episode["case_seed"] = episode_seed
    episode["official_count_generated"] = len(sources)
    return episode


def summarize_episodes(episodes, *, seed=None):
    """按 B 题口径汇总：清除比例、平均定位清除时间、阶段时间均值。"""
    counts = Counter(episode["cleared_count"] for episode in episodes)
    cleared_total = sum(episode["cleared_count"] for episode in episodes)
    generated_total = sum(episode["official_count_generated"]
                          for episode in episodes)
    accounting_failures = [index for index, episode in enumerate(episodes)
                           if not episode["recon"]["accounting_ok"]]
    return {
        "episode_count": len(episodes),
        "cleared_total": cleared_total,
        "generated_total": generated_total,
        "cleared_fraction": (cleared_total / generated_total
                             if generated_total else None),
        "all_sources_cleared": all(
            episode["cleared_count"] == episode["official_count_generated"]
            for episode in episodes),
        "per_episode_cleared_counts": dict(sorted(counts.items())),
        "average_clear_time_s": (
            sum(episode["average_clear_time_s"] or 0.0
                for episode in episodes) / len(episodes)
            if episodes else None),
        "virtual_time_mean_s": (
            sum(episode["virtual_time_s"] for episode in episodes)
            / len(episodes) if episodes else None),
        "scan_time_mean_s": (
            sum(episode["breakdown"]["scan_s"] for episode in episodes)
            / len(episodes) if episodes else None),
        "resolve_time_mean_s": (
            sum(episode["breakdown"]["resolve_s"] for episode in episodes)
            / len(episodes) if episodes else None),
        "clear_action_time_mean_s": (
            sum(episode["breakdown"]["clear_action_s"]
                for episode in episodes) / len(episodes)
            if episodes else None),
        "accounting_failure_count": len(accounting_failures),
        "accounting_failure_indices": accounting_failures,
        "seed": seed,
    }


def write_report(payload, path):
    """把批量回放结果写成 JSON（供人工/Claude 读取）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    return path


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="simlite 批量回放统计")
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--seed", type=int, default=20260912)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--output", type=str,
                        default="output/simlite_replay.json")
    args = parser.parse_args()
    from q3.policy import Q3Policy

    started = time.perf_counter()
    payload = replay_batch(
        lambda: Q3Policy(),
        args.count,
        seed=args.seed,
        workers=args.workers,
    )
    payload["elapsed_wall_s"] = time.perf_counter() - started
    write_report(payload, args.output)
    summary = payload["summary"]
    print(f"局数 {summary['episode_count']}，清除 {summary['cleared_total']}"
          f"/{summary['generated_total']}（{summary['cleared_fraction']:.2%}），"
          f"全清局 {sum(1 for e in payload['episodes'] if e['cleared_count']==e['official_count_generated'])}")
    print(f"平均定位清除时间 {summary['average_clear_time_s']:.1f} s/源，"
          f"局均虚拟时间 {summary['virtual_time_mean_s']:.0f} s")
    print(f"阶段均值：扫描 {summary['scan_time_mean_s']:.0f} s / "
          f"resolve {summary['resolve_time_mean_s']:.0f} s / "
          f"清除动作 {summary['clear_action_time_mean_s']:.0f} s；"
          f"对账失败 {summary['accounting_failure_count']} 局")
    print(f"输出：{args.output}")