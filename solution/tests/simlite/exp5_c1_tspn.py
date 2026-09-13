"""[实验轮5-组合1] M9 近邻序 + tspn_clear 增量同池对比（300 局级）。

臂 A= Q3BatchPolicy()（磁盘默认，含 M9 近邻序）；臂 B= Q3BatchPolicy(tspn_clear=True)。
验证轮3 已翻的 TSPN 在 M9 组合内的增量收益与门1。
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
    return Q3BatchPolicy()


def make_tspn():
    return Q3BatchPolicy(tspn_clear=True)


def main():
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 120
    seed_start = int(sys.argv[2]) if len(sys.argv) > 2 else 20981000
    workers = max(1, (os.cpu_count() or 4) - 2)
    seeds = list(range(seed_start, seed_start + count))
    started = time.perf_counter()
    payload = paired_compare(make_base, make_tspn, seeds, workers=workers)
    payload["meta"] = {
        "arm_a": "near_order_default", "arm_b": "near_order+tspn_clear",
        "count": count, "seed_start": seed_start, "workers": workers,
        "elapsed_s": round(time.perf_counter() - started, 1),
    }
    out = Path(__file__).with_name("analysis") / "exp5_c1_tspn.json"
    write_paired_report(payload, out)
    summary, gate = payload["summary"], payload["gate"]
    print(f"局数 {count}，墙钟 {payload['meta']['elapsed_s']}s")
    for key, item in summary.items():
        if key == "episode_count":
            continue
        diff = item["difference"]
        print(f"- {item['label']}: A med {item['a']['median']} / "
              f"B med {item['b']['median']}（中位差 {diff['median']}），"
              f"B 更优 {item['b_better']} / 更差 {item['b_worse']}")
    print(f"门1: {gate}")
    print(f"wrote: {out}")


if __name__ == "__main__":
    main()