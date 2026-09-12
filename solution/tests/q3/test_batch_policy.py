"""B2 批量解耦策略与 Held-Karp TSP 的测试（夜间自主优化）。"""

import itertools
import math
from pathlib import Path
import random
import sys
import unittest

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from q3.batch_policy import Q3BatchPolicy, held_karp_tsp
from simlite import Simulator, generate_sources
from simlite.replay import run_episode


class TspTestbench(unittest.TestCase):
    def test_tsp_matches_bruteforce_for_small_n(self):
        for n in (1, 2, 4, 6, 8):
            rng = random.Random(100 + n)
            points = [(rng.uniform(-1800, 1800), rng.uniform(-1800, 1800))
                      for _ in range(n)]
            total, order = held_karp_tsp(points)
            self.assertEqual(len(order), n)
            brute = min(
                sum(math.dist(points[perm[k + 1]], points[perm[k]])
                    for k in range(n - 1))
                for perm in itertools.permutations(range(n)))
            self.assertAlmostEqual(total, brute)

    def test_tsp_covers_every_point_once(self):
        rng = random.Random(7)
        points = [(rng.uniform(0, 100), rng.uniform(0, 100)) for _ in range(5)]
        _, order = held_karp_tsp(points)
        self.assertEqual(sorted(order), list(range(5)))


class BatchPolicyTestbench(unittest.TestCase):
    # 端到端局数受规划墙钟约束（FIM 规划 ~6s/次）；测试用 2s 预算加速，
    # 语义（状态机/清除完整性）不变，完整吞吐对比在 exp5_batch.py。
    def _policy(self):
        return Q3BatchPolicy(fim_cpu_time_limit_s=2.0)

    def test_batch_policy_clears_full_episode(self):
        rng = random.Random(20260912)
        sources = generate_sources(rng)
        episode = run_episode(self._policy(), Simulator(sources))
        self.assertEqual(episode["cleared_count"], len(sources))
        self.assertEqual(episode["cleared_count"] + episode["absent_count"],
                         20)
        self.assertTrue(episode["recon"]["accounting_ok"])
        self.assertLess(episode["action_count"], 10_000)

    def test_batch_policy_runs_two_seeds(self):
        for seed in (20260912, 20260913):
            rng = random.Random(seed)
            sources = generate_sources(rng)
            episode = run_episode(self._policy(), Simulator(sources))
            self.assertEqual(episode["cleared_count"], len(sources),
                             f"seed {seed} 未全清")


if __name__ == "__main__":
    unittest.main()