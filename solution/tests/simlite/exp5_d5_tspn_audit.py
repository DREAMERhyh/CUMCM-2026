"""[实验轮5-诊断5] TSPN 收益分层审计：clear 时刻区域半径 r 分布。

回答：TSPN 邻域（20-r）的真实贡献集中在哪些源？"压 r"该下注在哪里？
对磁盘默认批量流程采样：每局记录每次 clear 时的 region MEC 半径 r、
该源 discovery 距离、r 分层统计与邻域有效半径（20-r）。
"""

import json
import random
import statistics
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from q3.batch_policy import Q3BatchPolicy
from simlite import Simulator, generate_sources

ENTRY = "output/sim/debug_audit.jsonl"


def main():
    games = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    seed0 = int(sys.argv[2]) if len(sys.argv) > 2 else 20930000
    radii = []          # clear 时刻的区域半径
    discovery_dist = [] # 首次观测与源的距离（近似：区域中心与发现点）
    by_type = {"certified": [], "strip": []}
    for seed in range(seed0, seed0 + games):
        rng = random.Random(seed)
        sources = generate_sources(rng)
        sim = Simulator(sources)
        policy = Q3BatchPolicy()
        state = policy.initial_state()
        runs = 0
        for _ in range(10000):
            action = policy.next_action(state)
            if action is None:
                break
            resp = sim.execute(action)
            policy.apply_response(state, action, resp)
            if action.kind == "clear" and resp["clear_result"] == "success":
                track = state.sources[action.channel]
                r = track.region["minimum_enclosing_circle"]["radius"]
                radii.append(r)
                by_type["certified" if r <= 19.9 else "strip"].append(r)
                runs += 1
            if action.kind == "exit":
                break
    n = len(radii)
    print(f"[TSPN 审计] {n} 次成功 clear（{games} 局）")
    print(f"  r 分布：中位 {statistics.median(radii):.1f}，P25 "
          f"{sorted(radii)[n//4]:.1f}，P90 {sorted(radii)[int(0.9*n)]:.1f}，"
          f"max {max(radii):.1f}")
    for kind, values in by_type.items():
        if values:
            print(f"  {kind}: {len(values)} 个（r 中位 "
                  f"{statistics.median(values):.1f}）")
    # 邻域有效半径 20-r：>0 的源数占比
    useful = sum(1 for r in radii if r < 19.9)
    print(f"  邻域有效（20-r>0.1）：{useful}/{n} = {useful/n:.1%}")
    # 每源贡献估算：r<10 的源（邻域 >10m）占比
    big = sum(1 for r in radii if r < 10.0)
    print(f"  r<10（邻域>10m）：{big}/{n} = {big/n:.1%}")


if __name__ == "__main__":
    main()