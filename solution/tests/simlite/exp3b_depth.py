"""[夜间自主] 阶段3b：搜索深度实验重开（diameter 目标下，端到端总虚拟时间口径）。

此前"120 迭代档 +0.02% 关闭"结论仅对 FIM 目标有效；本实验在连续直径
目标下重开 120/600/3000 三档。端到端口径：Q3Policy 全流程虚拟时间
（含 resolve 的规划效应）。用法：
python tests/simlite/exp3b_depth.py [每档局数] [seed起始]
"""

import os
import sys
import time
from dataclasses import replace
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from q3.policy import Q3Policy
from simlite.paired import paired_compare, write_paired_report

LEVELS = [120, 600, 3000]


def _make_diameter(level):
    policy = Q3Policy(continuous_objective="diameter")
    scaling = level // 120
    policy.q2_config = replace(
        policy.q2_config,
        fim_max_iterations=level,
        fim_seed_limit=10 * scaling,
        fim_min_step_m=2.0 / scaling,
    )
    return policy


def make_d120():
    return _make_diameter(120)


def make_d600():
    return _make_diameter(600)


def make_d3000():
    return _make_diameter(3000)


def main():
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    seed_start = int(sys.argv[2]) if len(sys.argv) > 2 else 20910000
    workers = max(1, (os.cpu_count() or 4) - 2)
    seeds = list(range(seed_start, seed_start + count))
    started = time.perf_counter()
    reports = {}
    pairs = ((make_d120, make_d600, 600), (make_d120, make_d3000, 3000))
    for factory_a, factory_b, level in pairs:
        payload = paired_compare(factory_a, factory_b, seeds,
                                 workers=workers)
        payload["meta"] = {
            "objective": "diameter",
            "arm_a": "max_iterations=120",
            "arm_b": f"max_iterations={level}",
            "count": count, "seed_start": seed_start,
            "elapsed_s": round(time.perf_counter() - started, 1),
        }
        reports[f"level_{level}"] = payload
        summary, gate = payload["summary"], payload["gate"]
        print(f"--- 迭代 120 vs {level}（局数 {count}）---")
        for key, item in summary.items():
            if key == "episode_count":
                continue
            diff = item["difference"]
            print(f"- {item['label']}: A med {item['a']['median']} / "
                  f"B med {item['b']['median']}（中位差 {diff['median']}），"
                  f"B 更优 {item['b_better']} / 更差 {item['b_worse']}")
        print(f"门1: {gate}")
    payload = {"meta": {"objective": "diameter", "count": count,
                        "seed_start": seed_start},
               "levels": LEVELS, "reports": {
                   key: {"summary": value["summary"],
                         "gate": value["gate"]}
                   for key, value in reports.items()}}
    out = Path(__file__).with_name("analysis") / "exp3b_depth_diameter.json"
    write_paired_report(payload, out)
    print(f"wrote: {out}")


if __name__ == "__main__":
    main()