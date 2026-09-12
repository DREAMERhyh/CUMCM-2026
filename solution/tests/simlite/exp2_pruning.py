"""[夜间自主] 阶段2：A1+A6 排除圆修剪 门1 同池对比。

臂 A（基线）= Q3Policy() 全默认；臂 B（候选）= Q3Policy(use_no_signal_pruning=True)。
用法：python tests/simlite/exp2_pruning.py [局数] [seed起始]
"""

import os
import sys
import time
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from q3.policy import Q3Policy
from simlite.paired import paired_compare, write_paired_report


def make_base():
    return Q3Policy()


def make_prune():
    return Q3Policy(use_no_signal_pruning=True)


def main():
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    seed_start = int(sys.argv[2]) if len(sys.argv) > 2 else 20260912
    workers = max(1, (os.cpu_count() or 4) - 2)
    seeds = list(range(seed_start, seed_start + count))
    started = time.perf_counter()
    payload = paired_compare(make_base, make_prune, seeds, workers=workers)
    payload["meta"] = {
        "arm_a": "baseline(q3 defaults)",
        "arm_b": "use_no_signal_pruning=True",
        "count": count, "seed_start": seed_start, "workers": workers,
        "elapsed_s": round(time.perf_counter() - started, 1),
    }
    out = Path(__file__).with_name("analysis") / "exp2_pruning.json"
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