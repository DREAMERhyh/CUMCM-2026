"""[夜间自主] 收尾：最终组合验证——夜间最终默认 vs 晨间锁定基线。

臂 A（晨间锁定基线）= Q3Policy(use_optimal_stop=False)（交错 + 无 A3，
pure_ring8 + max_actions 8000 由入口参数承担）；
臂 B（夜间最终默认）= Q3BatchPolicy()（批量解耦 + A3 默认开）。
同池全量对比；报告 cleared 逐局不降、总时间统计、逐局最坏恶化。
用法：python tests/simlite/exp_final.py [局数] [seed起始]
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


def make_morning_baseline():
    return Q3Policy(use_optimal_stop=False)


def make_night_final():
    return Q3BatchPolicy()


def main():
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 120
    seed_start = int(sys.argv[2]) if len(sys.argv) > 2 else 20930000
    workers = max(1, (os.cpu_count() or 4) - 2)
    seeds = list(range(seed_start, seed_start + count))
    started = time.perf_counter()
    payload = paired_compare(make_morning_baseline, make_night_final,
                             seeds, workers=workers)
    payload["meta"] = {
        "arm_a": "morning_baseline(interleaved,no_A3)",
        "arm_b": "night_final(batch,use_optimal_stop)",
        "count": count, "seed_start": seed_start, "workers": workers,
        "elapsed_s": round(time.perf_counter() - started, 1),
    }
    out = Path(__file__).with_name("analysis") / "exp_final.json"
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