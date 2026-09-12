"""[实验轮3-P5] 顶配按 N 分档对地板（任务0 表格的实测列）。

用法：python tests/simlite/exp3_p5_floor.py [局数] [seed起始]
输出：每 N 档的中位总虚拟/均时/源 与地板表对照；压测层（R=1000 贴边、
N=16）由 seed 采样保证覆盖（simlite 源生成 = 均匀面积分布，贴边本就
大量出现）。
"""

import json
import os
import statistics
import sys
import time
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from q3.batch_policy import Q3BatchPolicy
from simlite.paired import paired_compare
from simlite.replay import run_episode
from simlite import Simulator, generate_sources
import random

FLOOR = {10: {"total": 4160, "per_source": 396},
         13: {"total": 4540, "per_source": 340},
         16: {"total": 5070, "per_source": 304}}


def make_top():
    return Q3BatchPolicy(interleaved_scan_refine=True, tour_refine=True)


def main():
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 90
    seed_start = int(sys.argv[2]) if len(sys.argv) > 2 else 20950000
    workers = max(1, (os.cpu_count() or 4) - 2)
    seeds = list(range(seed_start, seed_start + count))
    by_src = {}
    started = time.perf_counter()
    if workers == 1:
        results = [_one(seed) for seed in seeds]
    else:
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(max_workers=workers) as executor:
            results = list(executor.map(_one, seeds))
    for seed, episode in zip(seeds, results):
        src = episode["cleared_count"]
        by_src.setdefault(src, []).append(episode["virtual_time_s"])
    print(f"{'N':>4}{'样本':>6}{'中位总虚拟s':>12}{'均时/源':>10}"
          f"{'地板总':>10}{'地板均时':>10}{'差距%':>8}")
    rows = {}
    for src in sorted(by_src):
        values = sorted(by_src[src])
        med = statistics.median(values)
        per = med / src
        floor = FLOOR.get(src)
        gap = (med / floor["total"] - 1) * 100 if floor else None
        rows[src] = {"n": len(values), "median_total": med, "per_source": per}
        print(f"{src:>4}{len(values):>6}{med:>12.0f}{per:>10.1f}"
              f"{(floor['total'] if floor else 0):>10.0f}"
              f"{(floor['per_source'] if floor else 0):>10.1f}"
              f"{(f'{gap:.0f}%' if gap is not None else '-'):>8}")
    out = Path(__file__).with_name("analysis") / "exp3_p5_floor.json"
    out.write_text(json.dumps(
        {"by_source": {str(k): v for k, v in rows.items()},
         "meta": {"count": count, "seed_start": seed_start,
                  "elapsed_s": round(time.perf_counter() - started, 1)}},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"墙钟 {round(time.perf_counter() - started, 1)}s；wrote: {out}")


def _one(seed):
    rng = random.Random(seed)
    sources = generate_sources(rng)
    episode = run_episode(make_top(), Simulator(sources), max_actions=10000)
    episode["cleared_count"] = len(sources)
    return seed, episode


if __name__ == "__main__":
    main()