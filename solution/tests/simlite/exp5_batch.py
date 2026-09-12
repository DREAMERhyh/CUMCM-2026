"""[夜间自主] 阶段5：B2 批量解耦（TSP） vs 交错流程 同池对比。

臂 A= Q3Policy()（交错，现状）；臂 B= Q3BatchPolicy()（全部定位后
Held-Karp TSP 排序清除）。用法：python tests/simlite/exp5_batch.py [局数]
"""

import os
import sys
import time
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from q3.batch_policy import Q3BatchPolicy
from q3.policy import Q3Policy
from simlite.paired import paired_compare, write_paired_report


def make_base():
    # 显式关闭 A3（其已是默认）：保证本实验只测"交错 vs 批量"这一个变量。
    return Q3Policy(use_optimal_stop=False)


def make_batch():
    return Q3BatchPolicy(use_optimal_stop=False)


def main():
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 120
    seed_start = int(sys.argv[2]) if len(sys.argv) > 2 else 20920000
    workers = max(1, (os.cpu_count() or 4) - 2)
    seeds = list(range(seed_start, seed_start + count))
    started = time.perf_counter()
    payload = paired_compare(make_base, make_batch, seeds, workers=workers)
    payload["meta"] = {
        "arm_a": "interleaved(default)", "arm_b": "batch+tsp",
        "count": count, "seed_start": seed_start, "workers": workers,
        "elapsed_s": round(time.perf_counter() - started, 1),
    }
    out = Path(__file__).with_name("analysis") / "exp5_batch.json"
    write_paired_report(payload, out)
    summary, gate = payload["summary"], payload["gate"]
    print(f"局数 {count}，墙钟 {payload['meta']['elapsed_s']}s")
    for key, item in summary.items():
        if key == "episode_count":
            continue
        diff = item["difference"]
        print(f"- {item['label']}: A med {item['a']['median']} / "
              f"B med {item['b']['median']}（中位差 {diff['median']}），"
              f"B 更优 {item['b_better']} / 持平 {item['tie']} / "
              f"更差 {item['b_worse']}，最坏恶化 {item['max_b_minus_a']}")
    print(f"门1: {gate}")
    print(f"wrote: {out}")


if __name__ == "__main__":
    main()