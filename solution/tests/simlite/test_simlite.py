"""simlite 验收测试：附件2 官方 199 秒示例、Q3 端到端对账、语义单测、批量回放。"""

import math
from pathlib import Path
import random
import sys
import unittest

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from common.models import Action
from q3.policy import Q3Policy
from simlite import (RequestIdConflictError, Simulator, Source,
                     _fixed_error, _in_coverage, generate_sources)
from simlite.replay import replay_batch, run_episode


class Official199ExampleTestbench(unittest.TestCase):
    """验收硬标准1：逐项复现附件2 第10节的官方 199 秒示例。"""

    def test_official_199_second_example_timeline(self):
        simulator = Simulator([])  # 无源，纯计时
        actions = [
            Action("enter", "enter-1"),
            Action("measure", "measure-1", (300.0, 400.0), 1),
            Action("measure", "measure-2", (300.0, 400.0), 2),
            Action("clear", "clear-1", (300.0, 0.0), 3),
            Action("measure", "measure-3", (300.0, 0.0), 2),
            Action("exit", "exit-1"),
        ]
        expected = [0.0, 105.0, 111.0, 194.0, 199.0, 199.0]
        for action, moment in zip(actions, expected):
            response = simulator.execute(action)
            self.assertTrue(response["accepted"])
            self.assertEqual(response["virtual_time_s"], moment)
        # 频道语义：clear 不切换频道；第 5 步同频道检测没有切换耗时。
        self.assertEqual(simulator.channel, 2)
        self.assertEqual(simulator.position, (300.0, 0.0))


class SourceGenerationTestbench(unittest.TestCase):
    def test_default_count_and_uniqueness(self):
        rng = random.Random(20260912)
        sources = generate_sources(rng)
        self.assertTrue(10 <= len(sources) <= 16)
        channels = [source.channel for source in sources]
        self.assertEqual(len(channels), len(set(channels)))
        self.assertEqual([source.direction_deg for source in sources],
                         [None] * len(sources))

    def test_all_sources_inside_disk_with_valid_radius(self):
        rng = random.Random(7)
        for source in generate_sources(rng, count=16):
            self.assertLessEqual(math.hypot(*source.position), 1800.0)
            self.assertTrue(1000.0 <= source.receive_radius <= 1500.0)

    def test_seed_reproducibility(self):
        first = generate_sources(random.Random(42), count=12)
        second = generate_sources(random.Random(42), count=12)
        self.assertEqual([(s.channel, s.position, s.receive_radius)
                          for s in first],
                         [(s.channel, s.position, s.receive_radius)
                          for s in second])

    def test_directional_sources_ratio(self):
        rng = random.Random(1)
        sources = generate_sources(rng, count=10, direction_ratio=1.0)
        self.assertTrue(all(s.direction_deg is not None
                            for s in sources))


class MeasureSemanticsTestbench(unittest.TestCase):
    def setUp(self):
        self.source = Source(3, (500.0, 400.0), 1100.0)  # 全向源

    def _simulator(self):
        return Simulator([self.source])

    def test_direction_within_range(self):
        simulator = self._simulator()
        simulator.execute(Action("enter", "e"))
        response = simulator.execute(
            Action("measure", "m", (0.0, 0.0), 3))
        self.assertEqual(response["measure_result"], "direction")
        self.assertTrue(0.0 <= response["svd_deg"] < 360.0)

    def test_direction_error_is_fixed_per_location(self):
        simulator = self._simulator()
        simulator.execute(Action("enter", "e"))
        first = simulator.execute(Action("measure", "m1", (0.0, 0.0), 3))
        second = simulator.execute(Action("measure", "m2", (0.0, 0.0), 3))
        self.assertEqual(first["svd_deg"], second["svd_deg"])
        # 误差有界于 ±1°（svd 已按 [0,360) 归一化）。
        true = math.degrees(math.atan2(
            self.source.position[1], self.source.position[0])) % 360.0
        error = (first["svd_deg"] - true) % 360.0
        self.assertLessEqual(min(error, 360.0 - error), 1.0)
        self.assertAlmostEqual(
            _fixed_error((0.0, 0.0), 3),
            _fixed_error((0.0, 0.0), 3),
        )
        self.assertTrue(-1.0 <= _fixed_error((0.0, 0.0), 3) <= 1.0)

    def test_no_signal_beyond_receive_radius(self):
        simulator = Simulator([Source(3, (1700.0, 100.0), 1000.0)])
        simulator.execute(Action("enter", "e"))
        response = simulator.execute(
            Action("measure", "m", (-1000.0, 100.0), 3))  # 距离 2700
        self.assertEqual(response["measure_result"], "no_signal")

    def test_near_within_5m(self):
        simulator = Simulator([Source(3, (3.0, 4.0), 1000.0)])
        simulator.execute(Action("enter", "e"))
        response = simulator.execute(
            Action("measure", "m", (0.0, 0.0), 3))  # 距离 5
        self.assertEqual(response["measure_result"], "near")

    def test_directional_source_outside_coverage_is_no_signal(self):
        # 定向方向 0°（正东）：覆盖 = 东半平面（±90°含边界）。
        source = Source(3, (0.0, 0.0), 1500.0, direction_deg=0.0)
        simulator = Simulator([source])
        simulator.execute(Action("enter", "e"))
        response = simulator.execute(
            Action("measure", "m", (-1000.0, 0.0), 3))  # 正西：夹角 180°
        self.assertEqual(response["measure_result"], "no_signal")
        self.assertFalse(_in_coverage(source, (-1000.0, 0.0)))

    def test_directional_source_boundary_is_covered(self):
        # 正北/正南与正东夹角恰为 90°：覆盖边界（含）内，应可见。
        source = Source(3, (0.0, 0.0), 1500.0, direction_deg=0.0)
        self.assertTrue(_in_coverage(source, (0.0, 1000.0)))
        self.assertTrue(_in_coverage(source, (0.0, -1000.0)))
        simulator = Simulator([source])
        simulator.execute(Action("enter", "e"))
        response = simulator.execute(
            Action("measure", "m", (0.0, 1000.0), 3))
        self.assertEqual(response["measure_result"], "direction")

    def test_directional_source_inside_coverage(self):
        source = Source(3, (0.0, 0.0), 1500.0, direction_deg=0.0)
        simulator = Simulator([source])
        simulator.execute(Action("enter", "e"))
        response = simulator.execute(
            Action("measure", "m", (1000.0, 0.0), 3))  # 正东，在覆盖内
        self.assertEqual(response["measure_result"], "direction")


class ClearSemanticsTestbench(unittest.TestCase):
    def test_clear_success_and_repeat_clear_fails(self):
        simulator = Simulator([Source(3, (10.0, 10.0), 1000.0)])
        simulator.execute(Action("enter", "e"))
        first = simulator.execute(Action("clear", "c1", (0.0, 0.0), 3))
        # 源距清除点 14.14m ≤ 20m：成功；原地清除 = 0 移动 + 5s。
        self.assertEqual(first["clear_result"], "success")
        self.assertAlmostEqual(first["virtual_time_s"], 5.0)
        second = simulator.execute(Action("clear", "c2", (0.0, 0.0), 3))
        self.assertEqual(second["clear_result"], "no_target_in_range")

    def test_clear_does_not_switch_channel(self):
        simulator = Simulator([Source(3, (10.0, 10.0), 1000.0)])
        simulator.execute(Action("enter", "e"))
        simulator.execute(Action("measure", "m", (10.0, 10.0), 5))
        self.assertEqual(simulator.channel, 5)
        before = simulator.virtual_time_s
        simulator.execute(Action("clear", "c", (10.0, 10.0), 3))
        after = simulator.virtual_time_s
        self.assertEqual(simulator.channel, 5)
        self.assertAlmostEqual(after - before, 5.0)  # 原地清除成功：0+5s

    def test_clear_time_budget_success_vs_miss(self):
        simulator = Simulator([Source(3, (0.0, 0.0), 1000.0)])
        simulator.execute(Action("enter", "e"))
        hit = simulator.execute(Action("clear", "c1", (0.0, 0.0), 3))
        miss = simulator.execute(Action("clear", "c2", (0.0, 0.0), 3))
        self.assertEqual(hit["clear_result"], "success")
        self.assertEqual(miss["clear_result"], "no_target_in_range")
        self.assertAlmostEqual(hit["virtual_time_s"], 5.0)  # 原地成功
        self.assertAlmostEqual(miss["virtual_time_s"] - hit["virtual_time_s"],
                               3.0)  # 重复清除：只花定位 3s

    def test_rejected_before_enter(self):
        simulator = Simulator([])
        response = simulator.execute(
            Action("measure", "m", (0.0, 0.0), 1))
        self.assertFalse(response["accepted"])
        self.assertEqual(response["virtual_time_s"], 0)

    def test_idempotent_retry_and_conflict(self):
        simulator = Simulator([Source(3, (500.0, 400.0), 1100.0)])
        action = Action("measure", "same", (0.0, 0.0), 3)
        simulator.execute(Action("enter", "e"))
        first = simulator.execute(action)
        second = simulator.execute(action)
        self.assertEqual(first, second)
        simulator.execute(Action("measure", "ok", (0.0, 0.0), 3))
        with self.assertRaises(RequestIdConflictError):
            simulator.execute(
                Action("measure", "same", (100.0, 100.0), 3))  # 同 ID 不同动作


class PolicyEndToEndTestbench(unittest.TestCase):
    """验收硬标准2：Q3Policy 跑 simlite 一局，与 time_model 逐动作对账。"""

    def test_q3_policy_episode_accounts_correctly(self):
        rng = random.Random(20260912)
        sources = generate_sources(rng)
        simulator = Simulator(sources, error_bound_deg=1.0)
        episode = run_episode(Q3Policy(), simulator)
        self.assertTrue(episode["recon"]["accounting_ok"],
                        str(episode["recon"]))
        self.assertEqual(episode["cleared_count"] + episode["absent_count"],
                         20)
        self.assertEqual(
            sorted(episode["cleared_channels"]
                   + episode["absent_channels"]),
            list(range(1, 21)))
        self.assertGreater(episode["cleared_count"], 0)
        self.assertAlmostEqual(
            episode["breakdown"]["measure_action_s"],
            episode["breakdown"]["scan_s"]
            + episode["breakdown"]["resolve_s"]
            - episode["breakdown"]["clear_action_s"],
            delta=1e-6,
        )
        self.assertEqual(episode["breakdown"]["enter_exit_s"], 0.0)
        self.assertIsNotNone(episode["average_clear_time_s"])
        self.assertGreater(episode["average_clear_time_s"], 0.0)

    def test_scan_phase_matches_scan_layout_estimate_without_skips(self):
        # 全源都不可见/无源时，扫描阶段时间应等于
        # coverage.scan_phase_virtual_time(布局)（频道跳过的近似上界）。
        from q3.coverage import scan_phase_virtual_time
        simulator = Simulator([])
        episode = run_episode(Q3Policy(scan_layout="pure_ring8"),
                              simulator)
        estimated = scan_phase_virtual_time(
            Q3Policy(scan_layout="pure_ring8").coverage_points
        )["total_s"]
        # 无源时不会跳过频道：扫描段应为估算值（微秒累计与浮点重算差 <1ms）。
        self.assertAlmostEqual(episode["breakdown"]["scan_s"], estimated,
                               delta=1e-3)

    def test_replay_batch_two_episodes(self):
        payload = replay_batch(lambda: Q3Policy(), 2, seed=20260912,
                               workers=1)
        self.assertEqual(payload["summary"]["episode_count"], 2)
        for index, episode in enumerate(payload["episodes"]):
            self.assertEqual(episode["case_seed"], 20260912 + index)
            self.assertTrue(episode["recon"]["accounting_ok"])
            self.assertEqual(
                episode["cleared_count"] + episode["absent_count"], 20)
        self.assertEqual(payload["summary"]["accounting_failure_count"], 0)
        self.assertIsNotNone(payload["summary"]["cleared_fraction"])


if __name__ == "__main__":
    unittest.main()