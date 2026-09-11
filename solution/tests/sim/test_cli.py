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


if __name__ == "__main__":
    unittest.main()
