"""[实验轮3-P3] 交织扫描（扫描驻留点即免费 refine 腿）vs 现状批量，门1 快筛。

用法：python tests/simlite/exp3_p3_intscan.py [局数] [seed起始]
"""

import os
import sys
import time
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from q3.batch_policy import Q3BatchPolicy
from simlite.paired import paired_compare, write_paired_report


def make_base():
    return Q3BatchPolicy(interleaved_scan_refine=False,
                         use_optimal_stop=False)


def make_interleaved():
    return Q3BatchPolicy(interleaved_scan_refine=True,
                         use_optimal_stop=False)


def main():
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    seed_start = int(sys.argv[2]) if len(sys.argv) > 2 else 20970000
    workers = max(1, (os.cpu_count() or 4) - 2)
    seeds = list(range(seed_start, seed_start + count))
    started = time.perf_counter()
    payload = paired_compare(make_base, make_interleaved, seeds,
                             workers=workers)
    payload["meta"] = {
        "arm_a": "batch(scan skips found)", "arm_b": "interleaved scan refine",
        "count": count, "seed_start": seed_start, "workers": workers,
        "elapsed_s": round(time.perf_counter() - started, 1),
    }
    out = Path(__file__).with_name("analysis") / "exp3_p3_intscan.json"
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