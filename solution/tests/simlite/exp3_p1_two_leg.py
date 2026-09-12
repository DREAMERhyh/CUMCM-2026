"""[实验轮3-P1] J 方向预实验：两腿即证书可行性。

统计当前 simlite 批量流程中每源的 region 半径演进：
R0=发现后、R1=第1次 refine 后、R2=第2次 refine 后。
问题：(a) 2 腿（发现+1 交会）后 MEC<=19.9 的比例；
      (b) 每源 refine 次数分布（当前流程是否过度 refine）；
      (c) refine 点的"绕行代价"（refine 前后位置距离）分布——
          若动辄数百米，B 方向（顺路最小绕行）的收割空间确认。
"""

import math
import random
import statistics
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from q3.batch_policy import Q3BatchPolicy
from simlite import Simulator, generate_sources


def run_one(seed, max_actions=10000):
    rng = random.Random(seed)
    sources = generate_sources(rng)
    sim = Simulator(sources)
    policy = Q3BatchPolicy()
    state = policy.initial_state()
    tracks = {}
    last_pos = (0.0, 0.0)
    for _ in range(max_actions):
        action = policy.next_action(state)
        if action is None:
            break
        resp = sim.execute(action)
        if action.kind == "exit":
            break
        policy.apply_response(state, action, resp)
        if action.position is not None:
            hop = math.dist(action.position, last_pos)
            last_pos = action.position
            if action.kind == "measure" and resp["measure_result"] == "direction":
                channel = action.channel
                cur_radius = state.sources[channel].region[
                    "minimum_enclosing_circle"]["radius"]
                tracks.setdefault(channel, []).append(
                    (cur_radius, hop, resp["measure_result"]))
    return tracks


def main():
    games = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    seed0 = int(sys.argv[2]) if len(sys.argv) > 2 else 20930000
    r0 = r1 = r2 = 0
    total_sources = 0
    refine_hop = []          # 每次 refine 的移动距离
    unused_r1 = 0
    per_source_radius_after = []  # 每源2个方向观测后的最终半径
    for seed in range(seed0, seed0 + games):
        tracks = run_one(seed)
        for channel, entries in tracks.items():
            total_sources += 1
            radii = [e[0] for e in entries]
            hops = [e[1] for e in entries]
            r0 += radii[0] <= 19.9
            if len(radii) >= 2:
                r1 += radii[1] <= 19.9
                refine_hop.append(hops[1])
                per_source_radius_after.append(radii[1])
            if len(radii) >= 3:
                r2 += radii[2] <= 19.9
    n = total_sources
    print(f"[P1] 源样本 {n}（{games} 局）")
    print(f"  1 腿后 MEC<=19.9: {r0}/{n} = {r0/n:.1%}")
    print(f"  2 腿后 MEC<=19.9: {r1}/{n} = {r1/n:.1%}")
    print(f"  3+ 腿后 <=19.9:   {r2}/{n}")
    if refine_hop:
        print(f"  refine 腿移动距离：中位 {statistics.median(refine_hop):.0f}m, "
              f"P90 {sorted(refine_hop)[int(0.9*len(refine_hop))]:.0f}m, "
              f"max {max(refine_hop):.0f}m")
    if per_source_radius_after:
        print(f"  2 腿后半径（未达 19.9 的源）："
              f"{[round(r,1) for r in sorted(per_source_radius_after) if r > 19.9][:10]}")


if __name__ == "__main__":
    main()