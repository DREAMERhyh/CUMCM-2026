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
from sim.cli import main


class SimulatorCliOutputTestbench(unittest.TestCase):
    def test_policy_run_prints_average_virtual_time_per_cleared_source(self):
        summary = RunSummary(
            actions=[{}, {}],
            cleared_channels=[1, 3, 5, 7],
            virtual_time_s=800.0,
            exit_reason="user_exit",
        )
        output = io.StringIO()
        with (patch("sim.cli.HttpRobotClient"),
              patch("sim.cli.run_live_policy", return_value=summary),
              patch("sim.cli._count_successful_clears", return_value=4),
              redirect_stdout(output)):
            code = main([
                "--problem", "3",
                "--mode", "policy",
                "--robot-id", "offline-test",
                "--confirm-ready",
                "--confirm-policy",
            ])
        self.assertEqual(code, 0)
        self.assertIn("平均用时：200.000000 s/信号源", output.getvalue())

    def test_policy_cli_passes_selected_q2_version_to_q3(self):
        summary = RunSummary(
            actions=[], cleared_channels=[], virtual_time_s=0.0,
            exit_reason="user_exit",
        )
        output = io.StringIO()
        with (patch("sim.cli.HttpRobotClient"),
              patch("sim.cli.Q3Policy") as policy_class,
              patch("sim.cli.run_live_policy", return_value=summary),
              patch("sim.cli._count_successful_clears", return_value=0),
              redirect_stdout(output)):
            code = main([
                "--problem", "3", "--mode", "policy",
                "--robot-id", "offline-test",
                "--q2-version", "legacy",
                "--confirm-ready", "--confirm-policy",
            ])
        self.assertEqual(code, 0)
        self.assertEqual(
            policy_class.call_args.kwargs["q2_version"], "legacy"
        )
        self.assertEqual(
            policy_class.call_args.kwargs["failed_clear_remeasure_mode"],
            "gated",
        )

    def test_policy_cli_passes_selected_q2_version_to_q4(self):
        summary = RunSummary(
            actions=[], cleared_channels=[], virtual_time_s=0.0,
            exit_reason="user_exit",
        )
        output = io.StringIO()
        with (patch("sim.cli.HttpRobotClient"),
              patch("sim.cli.Q4Policy") as policy_class,
              patch("sim.cli.run_live_policy", return_value=summary),
              patch("sim.cli._count_successful_clears", return_value=0),
              redirect_stdout(output)):
            code = main([
                "--problem", "4", "--mode", "policy",
                "--robot-id", "offline-test",
                "--q2-version", "legacy",
                "--confirm-ready", "--confirm-policy",
            ])
        self.assertEqual(code, 0)
        self.assertEqual(
            policy_class.call_args.kwargs["q2_version"], "legacy"
        )
        self.assertEqual(
            policy_class.call_args.kwargs["scan_mode"], "triangular25"
        )
        self.assertEqual(
            policy_class.call_args.kwargs["q2_candidate_mode"],
            "hybrid_pareto",
        )
        self.assertEqual(
            policy_class.call_args.kwargs["failed_clear_remeasure_mode"],
            "gated",
        )
        self.assertEqual(
            policy_class.call_args.kwargs["directional_rolling_mode"],
            "scenario",
        )
        self.assertEqual(
            policy_class.call_args.kwargs["directional_rolling_risk_metric"],
            "cvar",
        )
        self.assertEqual(
            policy_class.call_args.kwargs[
                "directional_rolling_cpu_time_limit_s"
            ],
            3.0,
        )


if __name__ == "__main__":
    unittest.main()
