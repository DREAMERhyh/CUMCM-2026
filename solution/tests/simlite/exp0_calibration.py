"""[夜间自主] 阶段0：simlite 吞吐自校准。

实测单局墙钟、动作数分布（重点 14-16 源局）与 8000 动作上限裕量，
据此确定今夜每臂样本量（筛选 >=100/臂、晋级确认 >=300/臂，达不到就
报告实际达成量）。Windows spawn 要求策略工厂为模块级可 pickle 函数。
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

from q3.policy import Q3Policy
from simlite.replay import replay_batch


def make_q3():
    return Q3Policy()


def main():
    workers = max(1, (os.cpu_count() or 4) - 2)
    print(f"cpu_count={os.cpu_count()} workers={workers}（留 2 核）")
    started = time.perf_counter()
    payload = replay_batch(make_q3, 10, seed=20260912, workers=workers)
    elapsed = time.perf_counter() - started
    print(f"10 局并行墙钟：{elapsed:.1f}s")
    episodes = sorted(payload["episodes"], key=lambda e: e["case_seed"])
    rows = []
    for episode in episodes:
        rows.append({
            "seed": episode["case_seed"],
            "sources": episode["official_count_generated"],
            "cleared": episode["cleared_count"],
            "actions": episode["action_count"],
            "virtual_time_s": round(episode["virtual_time_s"], 1),
            "accounting_ok": episode["recon"]["accounting_ok"],
        })
    print(f"{'seed':>10}{'源数':>5}{'清除':>5}{'动作数':>8}{'虚拟s':>10}"
          f"{'对账':>5}")
    for row in rows:
        print(f"{row['seed']:>10}{row['sources']:>5}{row['cleared']:>5}"
              f"{row['actions']:>8}{row['virtual_time_s']:>10}"
              f"{str(row['accounting_ok']):>5}")
    actions = [row["actions"] for row in rows]
    print("动作数 min/med/max =",
          min(actions), statistics.median(actions), max(actions))
    print("8000 上限裕量：最坏局占比",
          f"{max(actions)/8000:.1%}（>=30% 裕量要求动作数 <=5600）")
    serial_estimate = elapsed  # 并行摊薄不代表串行单局成本
    print("JSONL 估算：动作数 x ~400B/行 ->",
          f"{max(actions)*400//1024} KB")
    out = Path(__file__).with_name("exp0_calibration.json")
    out.write_text(json.dumps(
        {"elapsed_s": elapsed, "workers": workers, "rows": rows},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote: {out}")


if __name__ == "__main__":
    main()