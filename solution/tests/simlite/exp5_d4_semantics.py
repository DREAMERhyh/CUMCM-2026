"""[实验轮5-诊断4] 双区域语义一致性测试。

问题：P2/minimax 五版腿选择失败，是"预测不真"还是"保证域语义错误"
（保证域内腿点对真源 no_signal）？
测试：采样 60 局，跟踪每个 refine 腿点（batch_refine / enroute_refine）
的 measure_result——若保证域语义正确，no_signal 率应 ≈0
（数学：腿点在保证域内 → 距可能源 ≤1000 ≤ R_真源 → 必收到）。
同时记录腿点与真源距离的分布（验证保守内近似边界行为）。
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


def main():
    games = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    seed0 = int(sys.argv[2]) if len(sys.argv) > 2 else 20930000
    leg_results = {"direction": 0, "no_signal": 0, "near": 0}
    far_distances = []
    for seed in range(seed0, seed0 + games):
        rng = random.Random(seed)
        sources = generate_sources(rng)
        sim = Simulator(sources)
        policy = Q3BatchPolicy()
        state = policy.initial_state()
        for _ in range(10000):
            action = policy.next_action(state)
            if action is None:
                break
            mode = state.pending_mode
            resp = sim.execute(action)
            policy.apply_response(state, action, resp)
            if action.kind == "exit":
                break
            if action.kind == "measure" and mode in (
                    "batch_refine", "enroute_refine"):
                # 该腿点对真源的距离（用 sim 的源表）
                true_source = sim.sources.get(action.channel)
                if true_source is not None:
                    far_distances.append(
                        __import__("math").dist(action.position,
                                                true_source.position))
                    leg_results[resp["measure_result"]] = (
                        leg_results.get(resp["measure_result"], 0) + 1)
    total = sum(leg_results.values())
    print(f"[诊断4] refine 腿点 {total} 个（{games} 局）")
    for key, value in leg_results.items():
        print(f"  {key}: {value} ({value/total:.2%})")
    if far_distances:
        print(f"  腿点-真源距离：中位 {statistics.median(far_distances):.0f}m，"
              f"P90 {sorted(far_distances)[int(0.9*len(far_distances))]:.0f}m，"
              f"max {max(far_distances):.0f}m")
    print("结论判定：no_signal 率 ≈0 → 保证域语义一致，预测路线死因=预测不真；"
          "no_signal 率 >1% → 语义错误，预测路线可复活潜力。")


if __name__ == "__main__":
    main()