"""[实验轮5-红队] 极端场景生成器与冒烟验证。

场景类：(a) 贴边源（ρ>=1700）；(b) R=1000 下界；(c) 源聚集（簇）；
(d) 局1 复现几何（单难源贴边 ρ≈1588 附近）。对 final 组合做 100% 清除
冒烟（每类 20 局）。
"""

import random
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from simlite import Source  # noqa: F401  (仅类型参考)


def generation_adversarial(seed):
    """红队源摆布：贴边 + 小 R + 局部聚集混合（覆盖最坏场景族）。"""
    rng = random.Random(seed)
    channels = list(range(1, 21))
    rng.shuffle(channels)
    count = rng.randint(10, 16)
    sources = []
    used_channels = channels[:count]
    for index, channel in enumerate(used_channels):
        mode = index % 4
        if mode == 0:
            # 贴边：ρ ∈ [1700, 1798]
            rho = rng.uniform(1700.0, 1798.0)
            angle = rng.uniform(0.0, 2.0 * 3.141592653589793)
        elif mode == 1:
            # R=1000 下界 + 贴边
            rho = rng.uniform(1600.0, 1795.0)
            angle = rng.uniform(0.0, 2.0 * 3.141592653589793)
        elif mode == 2:
            # 聚集：确定性围绕簇心（半径 <=300m 的环内）
            import math
            cluster_angle = rng.uniform(0.0, 2.0 * math.pi)
            cluster_radius = rng.uniform(0.0, 900.0)
            cluster = (cluster_radius * math.cos(cluster_angle),
                       cluster_radius * math.sin(cluster_angle))
            local_radius = rng.uniform(0.0, 300.0)
            local_angle = rng.uniform(0.0, 2.0 * math.pi)
            rho = local_radius
            angle = local_angle
            import math
            position = (cluster[0] + rho * math.cos(angle),
                        cluster[1] + rho * math.sin(angle))
            rho = math.hypot(*position) if math.hypot(*position) < 1790 else 1790
            angle = math.atan2(position[1], position[0]) if rho else 0.0
        else:
            rho = rng.uniform(0.0, 1790.0)
            angle = rng.uniform(0.0, 2.0 * 3.141592653589793)
        import math
        position = (rho * math.cos(angle), rho * math.sin(angle))
        receive = rng.uniform(1000.0, 1500.0)
        if mode == 1:
            receive = 1000.0
        sources.append(Source(channel, position, receive))
    return sources, {"count": count, "adversarial": True}


def main():
    games = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    seed0 = int(sys.argv[2]) if len(sys.argv) > 2 else 20990000
    from q3.batch_policy import Q3BatchPolicy
    from simlite import Simulator
    from simlite.replay import run_episode

    failed = 0
    for seed in range(seed0, seed0 + games):
        sources, meta = generation_adversarial(seed)
        episode = run_episode(Q3BatchPolicy(tspn_clear=True),
                              Simulator(sources))
        expected = len(sources)
        if episode["cleared_count"] != expected:
            failed += 1
            print(f"  RED-TEAM FAIL seed={seed}: cleared "
                  f"{episode['cleared_count']}/{expected} vt="
                  f"{episode['virtual_time_s']:.0f}")
    print(f"[红队] {games} 局极端场景：失败 {failed}，"
          f"通过率 {(games-failed)/games:.0%}")


if __name__ == "__main__":
    main()