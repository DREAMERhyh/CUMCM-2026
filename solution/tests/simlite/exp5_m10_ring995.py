"""[实验轮5-M10] 环半径 960→990 快筛（30 局）。

数学：pure_ring8(r) 的中心覆盖要求 r<=995（r=990 恰在边界，通过）；
外缘 d(22.5°,1800)=961m（r=990）比 r=960 的 984m 多 23m 余量；
贴边源（ρ~1800）到环点的距离随 r 增大而更小 → 更多源获得第 3 个
可观测停点（interleaved 免费腿）→ 难源率可能结构性下降。
臂 A= 磁盘默认（r=960）；臂 B= r=990 环停点。
"""

import os
import sys
import time
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from q3.batch_policy import Q3BatchPolicy
from q3.coverage import pure_ring_8
from simlite.paired import paired_compare, write_paired_report


def make_base():
    return Q3BatchPolicy()


def make_r990():
    return Q3BatchPolicy(coverage_points=pure_ring_8(990.0))


def main():
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    seed_start = int(sys.argv[2]) if len(sys.argv) > 2 else 20990000
    workers = max(1, (os.cpu_count() or 4) - 2)
    seeds = list(range(seed_start, seed_start + count))
    started = time.perf_counter()
    payload = paired_compare(make_base, make_r990, seeds, workers=workers)
    payload["meta"] = {
        "arm_a": "ring960(default)", "arm_b": "ring990",
        "count": count, "seed_start": seed_start, "workers": workers,
        "elapsed_s": round(time.perf_counter() - started, 1),
    }
    out = Path(__file__).with_name("analysis") / "exp5_m10_ring990.json"
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