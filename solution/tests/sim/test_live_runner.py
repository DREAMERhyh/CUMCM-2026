import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from common.models import Action
from sim.live_runner import run_live_policy


class State:
    def __init__(self):
        self.entered = False
        self.exited = False
        self.cleared = set()
        self.absent = set()
        self.virtual_time_s = 0.0
        self.sequence = 0


class TinyPolicy:
    def initial_state(self):
        return State()

    def next_action(self, state):
        state.sequence += 1
        kind = "enter" if not state.entered else "exit"
        return Action(kind, f"{kind}-{state.sequence}")

    def apply_response(self, state, action, response):
        state.virtual_time_s = response["virtual_time_s"]
        if action.kind == "enter":
            state.entered = True
        elif action.kind == "exit":
            state.exited = True


class EndlessPolicy(TinyPolicy):
    def next_action(self, state):
        state.sequence += 1
        if not state.entered:
            return Action("enter", f"enter-{state.sequence}")
        return Action("measure", f"measure-{state.sequence}", (0, 0), 1)


class StubClient:
    def __init__(self, remaining=1200):
        self.remaining = remaining
        self.actions = []

    def execute(self, action):
        self.actions.append(action)
        common = {
            "accepted": True,
            "real_timestamp_ms": 1760000000000,
            "virtual_time_s": 0,
        }
        if action.kind == "enter":
            return {
                **common,
                "max_virtual_duration_s": 360000,
                "max_real_duration_s": 1200,
                "remaining_real_duration_s": self.remaining,
            }
        if action.kind == "measure":
            return {**common, "measure_result": "no_signal"}
        return {**common, "exit_reason": "user_exit"}


class LiveRunnerTestbench(unittest.TestCase):
    def test_normal_run_writes_two_flushed_jsonl_records(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "run.jsonl"
            summary = run_live_policy(TinyPolicy(), StubClient(), log_path=path)
            lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(summary.exit_reason, "user_exit")
        self.assertEqual([line["action"]["kind"] for line in lines], ["enter", "exit"])

    def test_zero_remaining_time_forces_safety_exit(self):
        client = StubClient(remaining=0)
        with TemporaryDirectory() as directory:
            path = Path(directory) / "run.jsonl"
            summary = run_live_policy(
                EndlessPolicy(), client, log_path=path, exit_safety_margin_s=0
            )
            lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([action.kind for action in client.actions], ["enter", "exit"])
        self.assertEqual(lines[-1]["note"], "reality_deadline_safety_exit")
        self.assertEqual(summary.exit_reason, "user_exit")

    def test_action_cap_reserves_last_action_for_exit(self):
        client = StubClient()
        with TemporaryDirectory() as directory:
            path = Path(directory) / "run.jsonl"
            run_live_policy(
                EndlessPolicy(), client, log_path=path,
                max_actions=3, exit_safety_margin_s=0,
            )
            lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([action.kind for action in client.actions],
                         ["enter", "measure", "exit"])
        self.assertEqual(lines[-1]["note"], "action_cap_safety_exit")

    def test_existing_log_is_never_overwritten(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "run.jsonl"
            path.write_text("keep", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                run_live_policy(TinyPolicy(), StubClient(), log_path=path)
            self.assertEqual(path.read_text(encoding="utf-8"), "keep")

    def test_nonfinite_safety_margin_is_rejected_before_log_creation(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "run.jsonl"
            with self.assertRaises(ValueError):
                run_live_policy(
                    TinyPolicy(), StubClient(), log_path=path,
                    exit_safety_margin_s=float("nan"),
                )
            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
