"""[实验轮5-主攻1f] M9 locate 近邻序 快筛（30 局）。

臂 A= Q3BatchPolicy() 磁盘默认（频道号序）；臂 B= 近邻序（M9 已默认生效，
A 用显式频道序对照？——为单变量，本脚本 A=现默认（已含近邻序），B=显式
频道序恢复（旧行为）——方向：B 应为旧行为（更差），若 A 优则 M9 保留。
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


class _ChannelOrderPolicy(Q3BatchPolicy):
    """旧行为：locate 按频道号序（M9 之前的实现）。"""

    def _locate_next(self, state):
        located = set(state.certificate_ok)
        remaining = [channel for channel in sorted(state.sources)
                     if channel not in state.cleared
                     and channel not in located]
        return self._locate_step(state, remaining)


def make_old_order():
    return _ChannelOrderPolicy()


def main():
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    seed_start = int(sys.argv[2]) if len(sys.argv) > 2 else 20980000
    workers = max(1, (os.cpu_count() or 4) - 2)
    seeds = list(range(seed_start, seed_start + count))
    started = time.perf_counter()
    payload = paired_compare(make_old_order, make_base, seeds,
                             workers=workers)
    payload["meta"] = {
        "arm_a": "channel_order(old, M9-off)", "arm_b": "nearest_order(M9)",
        "count": count, "seed_start": seed_start, "workers": workers,
        "elapsed_s": round(time.perf_counter() - started, 1),
    }
    out = Path(__file__).with_name("analysis") / "exp5_m9_near.json"
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