"""[实验轮6-猜4] 探针条带（probe_strip）快筛（30 局）。

臂 A= Q3BatchPolicy() 磁盘默认（strip 链保底）；臂 B= Q3BatchPolicy(probe_strip=True)
（蜂窝密排探针：r=27 区域 ~7-19 探针 vs 条带 76-228 点）。
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


def make_probe():
    return Q3BatchPolicy(probe_strip=True)


def main():
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    seed_start = int(sys.argv[2]) if len(sys.argv) > 2 else 20990000
    workers = max(1, (os.cpu_count() or 4) - 2)
    seeds = list(range(seed_start, seed_start + count))
    started = time.perf_counter()
    payload = paired_compare(make_base, make_probe, seeds, workers=workers)
    payload["meta"] = {
        "arm_a": "strip_default", "arm_b": "probe_strip=True",
        "count": count, "seed_start": seed_start, "workers": workers,
        "elapsed_s": round(time.perf_counter() - started, 1),
    }
    out = Path(__file__).with_name("analysis") / "exp6_c4_probe.json"
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