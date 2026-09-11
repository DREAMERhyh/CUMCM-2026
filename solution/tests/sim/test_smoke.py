from contextlib import redirect_stdout
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from common.models import RunSummary
from sim import cli as sim_cli
from sim.fake import FakeSimulator
from sim.cli import _average_time_line
from sim.smoke import SmokePolicy
from runtime.runner import run_policy


class SmokePolicyTestbench(unittest.TestCase):
    def test_average_time_console_line(self):
        self.assertEqual(
            _average_time_line(8000.0, 16),
            "平均用时：500.000000 s/信号源",
        )
        self.assertEqual(
            _average_time_line(5.0, 0),
            "平均用时：无法计算（未清除信号源）",
        )

    def test_q3_q4_policy_cli_prints_average_time(self):
        summary = RunSummary(
            actions=[{}, {}],
            cleared_channels=[3, 7],
            virtual_time_s=100.0,
            exit_reason="user_exit",
        )
        for problem in (3, 4):
            with self.subTest(problem=problem):
                output = io.StringIO()
                with (patch.object(sim_cli, "HttpRobotClient"),
                      patch.object(sim_cli, "run_live_policy",
                                   return_value=summary),
                      patch.object(sim_cli, "_count_successful_clears",
                                   return_value=2),
                      redirect_stdout(output)):
                    result = sim_cli.main([
                        "--problem", str(problem),
                        "--mode", "policy",
                        "--robot-id", "offline-test",
                        "--confirm-ready",
                        "--confirm-policy",
                    ])
                self.assertEqual(result, 0)
                self.assertIn(
                    "平均用时：50.000000 s/信号源",
                    output.getvalue(),
                )

    def test_smoke_sequence_is_enter_measure_exit(self):
        summary = run_policy(SmokePolicy(), FakeSimulator([]), max_actions=4)
        self.assertEqual(
            [item["action"]["kind"] for item in summary.actions],
            ["enter", "measure", "exit"],
        )
        self.assertEqual(summary.virtual_time_s, 5.0)
        self.assertEqual(summary.exit_reason, "user_exit")


if __name__ == "__main__":
    unittest.main()
