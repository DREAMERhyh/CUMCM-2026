"""sim/cli.py 的 --scan-layout 透传测试（Q3 默认策略为批量解耦 B2）。"""

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from common.models import Action
import sim.cli as sim_cli


class _CliSmokePolicy:
    def initial_state(self):
        return _State()

    def next_action(self, state):
        if not state.entered:
            return Action("enter", "e-1")
        return Action("exit", "x-1")

    def apply_response(self, state, action, response):
        if action.kind == "enter":
            state.entered = True


class _State:
    def __init__(self):
        self.entered = False
        self.virtual_time_s = 0.0


class _StubExchangeClient:
    def execute(self, action):
        return {
            "accepted": True,
            "real_timestamp_ms": 1760000000000,
            "virtual_time_s": 0.0,
            **({"max_virtual_duration_s": 360000,
                "max_real_duration_s": 1200,
                "remaining_real_duration_s": 1200}
               if action.kind == "enter" else
               {"exit_reason": "user_exit"} if action.kind == "exit" else
               {"measure_result": "no_signal"}),
        }


class SimCliScanLayoutTestbench(unittest.TestCase):
    def setUp(self):
        self._temporary = TemporaryDirectory()
        self.log_path = str(Path(self._temporary.name) / "run.jsonl")

    def tearDown(self):
        self._temporary.cleanup()

    def _call(self, *extra):
        return sim_cli.main([
            "--log", self.log_path, *extra,
        ])

    def test_invalid_scan_layout_is_rejected_by_choices(self):
        with self.assertRaises(SystemExit) as raised:
            self._call(
                "--problem", "3", "--mode", "policy", "--robot-id", "t",
                "--scan-layout", "ring9", "--confirm-ready",
                "--confirm-policy",
            )
        self.assertEqual(raised.exception.code, 2)

    def test_q3_policy_receives_scan_layout_kwarg(self):
        with patch("sim.cli.HttpRobotClient",
                   return_value=_StubExchangeClient()) as client_factory, \
             patch("sim.cli.Q3BatchPolicy",
                   return_value=_CliSmokePolicy()) as policy_factory:
            code = self._call(
                "--problem", "3", "--mode", "policy", "--robot-id", "t",
                "--scan-layout", "hub_ring6", "--confirm-ready",
                "--confirm-policy",
            )
        self.assertEqual(code, 0)
        client_factory.assert_called_once()
        self.assertEqual(policy_factory.call_count, 1)
        kwargs = policy_factory.call_args.kwargs
        self.assertEqual(kwargs["scan_layout"], "hub_ring6")
        self.assertEqual(kwargs["max_refinements"], 2)

    def test_q3_default_drops_scan_layout_kwarg(self):
        with patch("sim.cli.HttpRobotClient",
                   return_value=_StubExchangeClient()), \
             patch("sim.cli.Q3BatchPolicy",
                   return_value=_CliSmokePolicy()) as policy_factory:
            self._call(
                "--problem", "3", "--mode", "policy", "--robot-id", "t",
                "--confirm-ready", "--confirm-policy",
            )
        self.assertNotIn("scan_layout",
                         policy_factory.call_args.kwargs)

    def test_q4_never_builds_batch_policy(self):
        with patch("sim.cli.HttpRobotClient",
                   return_value=_StubExchangeClient()), \
             patch("sim.cli.Q3BatchPolicy") as batch_factory:
            code = self._call(
                "--problem", "4", "--mode", "policy", "--robot-id", "t",
                "--scan-layout", "pure_ring8", "--confirm-ready",
                "--confirm-policy",
            )
        self.assertEqual(code, 0)
        batch_factory.assert_not_called()


if __name__ == "__main__":
    unittest.main()