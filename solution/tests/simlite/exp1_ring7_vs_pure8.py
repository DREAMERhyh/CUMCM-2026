"""[夜间自主] 阶段1：ring7 vs pure_ring8 同池成对对比（E1 框架验收 + 论文数据）。

臂 A（基线）= ring7（旧默认），臂 B（候选）= pure_ring8（已锁定默认）。
验证 460s 离线扫描时间推算是否在端到端（含 resolve）中兑现。
用法：python tests/simlite/exp1_ring7_vs_pure8.py [局数] [seed起始]
"""

import json
import os
import sys
import time
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from q3.policy import Q3Policy
from simlite.paired import paired_compare, write_paired_report


def make_ring7():
    return Q3Policy(scan_layout="ring7")


def make_pure8():
    return Q3Policy(scan_layout="pure_ring8")


def main():
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    seed_start = int(sys.argv[2]) if len(sys.argv) > 2 else 20260912
    workers = max(1, (os.cpu_count() or 4) - 2)
    seeds = list(range(seed_start, seed_start + count))
    started = time.perf_counter()
    payload = paired_compare(make_ring7, make_pure8, seeds, workers=workers)
    payload["meta"] = {
        "arm_a": "ring7", "arm_b": "pure_ring8",
        "count": count, "seed_start": seed_start, "workers": workers,
        "elapsed_s": round(time.perf_counter() - started, 1),
    }
    out = Path(__file__).with_name("analysis") / "exp1_ring7_vs_pure8.json"
    write_paired_report(payload, out)
    summary, gate = payload["summary"], payload["gate"]
    print(f"局数 {count}，墙钟 {payload['meta']['elapsed_s']}s")
    for key, item in summary.items():
        if key == "episode_count":
            continue
        diff = item["difference"]
        print(f"- {item['label']}: A {item['a']['median']} / "
              f"B {item['b']['median']}（中位差 {diff['median']}），"
              f"B 更优 {item['b_better']} 局 / 持平 {item['tie']} / "
              f"更差 {item['b_worse']}，最坏恶化 {item['max_b_minus_a']}")
    print(f"门1: {gate}")
    print(f"wrote: {out}")


if __name__ == "__main__":
    main()