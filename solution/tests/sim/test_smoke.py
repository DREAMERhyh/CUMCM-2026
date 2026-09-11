from pathlib import Path
import sys
import unittest

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sim.fake import FakeSimulator
from sim.smoke import SmokePolicy
from runtime.runner import run_policy


class SmokePolicyTestbench(unittest.TestCase):
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
