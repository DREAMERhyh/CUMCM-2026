"""[夜间自主] 阶段7：E3 参数敏感性网格（error_deg / max_refinements vs 基线）。

每个参数档位作为一个候选臂，与基线（error_deg=1.005, max_refinements=2）
同池对比。error_deg 低于真实误差界（simlite 固定 ±1°）会破坏保守性，
必须单独报告清除缺失；max_refinements 影响 resolve 收敛成本。
用法：python tests/simlite/exp7_sensitivity.py [每臂局数] [seed起始]
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


def make_error_05():
    return Q3Policy(error_deg=0.5)


def make_error_15():
    return Q3Policy(error_deg=1.5)


def make_refine_0():
    return Q3Policy(max_refinements=0)


def make_refine_1():
    return Q3Policy(max_refinements=1)


def make_refine_4():
    return Q3Policy(max_refinements=4)


ARMS = [
    ("error_deg=0.5", make_error_05, "低于真实误差界 1°，保守性破坏风险"),
    ("error_deg=1.5", make_error_15, "过保守，区域膨胀"),
    ("max_refinements=0", make_refine_0, "无细化，直接 fallback"),
    ("max_refinements=1", make_refine_1, "单次细化"),
    ("max_refinements=4", make_refine_4, "更多细化机会"),
]


def main():
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    seed_start = int(sys.argv[2]) if len(sys.argv) > 2 else 20930000
    workers = max(1, (os.cpu_count() or 4) - 2)
    seeds = list(range(seed_start, seed_start + count))
    started = time.perf_counter()
    reports = {}
    for name, factory, note in ARMS:
        payload = paired_compare(make_base, factory, seeds, workers=workers)
        payload["meta"] = {"arm_a": "baseline", "arm_b": name,
                           "note": note, "count": count,
                           "seed_start": seed_start,
                           "elapsed_s": round(time.perf_counter() - started,
                                              1)}
        reports[name] = payload
        summary, gate = payload["summary"], payload["gate"]
        diff = summary["virtual_time_s"]["difference"]
        cleared_below = sum(1 for row in payload["rows"]
                            if row["b"]["cleared"] < row["a"]["cleared"])
        print(f"--- {name}: 虚拟时间中位差 {diff['median']:+.0f}s，"
              f"清除下降局 {cleared_below}/{count}，门1: "
              f"{'PASS' if gate['overall_pass'] else 'FAIL'} ---")
    payload = {"meta": {"count": count, "seed_start": seed_start},
               "reports": {key: {"summary": value["summary"],
                                 "gate": value["gate"],
                                 "meta": value["meta"]}
                           for key, value in reports.items()}}
    out = Path(__file__).with_name("analysis") / "exp7_sensitivity.json"
    write_paired_report(payload, out)
    print(f"wrote: {out}")


if __name__ == "__main__":
    main()